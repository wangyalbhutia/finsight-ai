from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.models import Transaction, User, AuditLog, StatementImport
from app.schemas.schemas import TransactionIn
import hashlib, csv, io
from decimal import Decimal, InvalidOperation
from datetime import datetime

router = APIRouter(prefix="/transactions", tags=["transactions"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # Stage 5: hard upload limit (audit finding)

def dedup_hash(user_id, date_, amount, merchant, description, type_):
    raw = f"{user_id}|{date_}|{amount}|{(merchant or '').lower().strip()}|{(description or '').lower().strip()}|{type_}"
    return hashlib.sha256(raw.encode()).hexdigest()

def out(t):
    return {"id": t.id, "user_id": t.user_id, "type": t.type, "amount": float(t.amount), "currency": getattr(t, "currency", "INR") or "INR",
            "category_name": t.category_name, "category_id": t.category_id, "account_id": t.account_id, "merchant": t.merchant,
            "description": t.description, "notes": t.notes or "", "date": t.date.isoformat(), "is_recurring": bool(t.is_recurring), "created_at": t.created_at.isoformat() if t.created_at else None}

@router.post("", status_code=201)
@router.post("/", status_code=201)
def create(data: TransactionIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    h = dedup_hash(current.id, data.date.isoformat(), str(data.amount), data.merchant, data.description, data.type)
    t = Transaction(user_id=current.id, type=data.type, amount=data.amount, currency=data.currency or "INR", category_name=data.category_name, category_id=data.category_id, account_id=data.account_id, merchant=data.merchant, description=data.description, notes=data.notes, date=data.date, is_recurring=data.is_recurring, dedup_hash=h)
    db.add(t); db.commit(); db.refresh(t); return out(t)

@router.get("")
@router.get("/")
def list_txns(db: Session = Depends(get_db), current: User = Depends(get_current_user), page: int = 1, limit: int = 50, page_size: int = None,
              type: str = None, category_name: str = None, category: str = None, search: str = None, start_date: str = None, end_date: str = None, min_amount: float = None, max_amount: float = None):
    # Filtering, search, counting and pagination are done in SQL — previously
    # every matching row was loaded and sliced in Python, which does not scale.
    page = max(1, page)
    size = min(max(1, page_size or limit), 200)
    q = db.query(Transaction).filter(Transaction.user_id == current.id)
    if type: q = q.filter(Transaction.type == type)
    cat = category_name or category
    if cat: q = q.filter(Transaction.category_name == cat)
    if start_date: q = q.filter(Transaction.date >= start_date)
    if end_date: q = q.filter(Transaction.date <= end_date)
    if min_amount is not None: q = q.filter(Transaction.amount >= min_amount)
    if max_amount is not None: q = q.filter(Transaction.amount <= max_amount)
    if search:
        s = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{s}%"
        q = q.filter(or_(Transaction.description.ilike(like, escape="\\"),
                         Transaction.merchant.ilike(like, escape="\\"),
                         Transaction.category_name.ilike(like, escape="\\")))
    total = q.count()
    sliced = q.order_by(Transaction.date.desc(), Transaction.id.desc()).offset((page - 1) * size).limit(size).all()
    items = [out(t) for t in sliced]
    return {"items": items, "transactions": items, "total": total, "page": page, "limit": size, "page_size": size}

@router.get("/export")
def export_csv(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    txns = db.query(Transaction).filter(Transaction.user_id == current.id).order_by(Transaction.date).all()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["date","type","amount","currency","category_name","merchant","description","notes","is_recurring"])
    for t in txns: w.writerow([t.date.isoformat(), t.type, str(t.amount), getattr(t,"currency","INR") or "INR", t.category_name, t.merchant, t.description, t.notes or "", str(bool(t.is_recurring)).lower()])
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})

@router.post("/import")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    content = await file.read()
    summary = {"accepted": 0, "rejected": 0, "duplicates": 0, "errors": [], "rejected_reasons": []}
    if len(content) > MAX_UPLOAD_BYTES:
        summary["rejected"] = 1
        summary["rejected_reasons"].append(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")
        summary["errors"] = summary["rejected_reasons"]
        return summary
    if not content or not content.strip():
        summary["rejected_reasons"].append("Empty file"); return summary
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        summary["rejected"] = 1; summary["rejected_reasons"].append("File is not valid UTF-8 text"); return summary
    return _import_csv_text(db, current, text, summary)


def _import_csv_text(db, current, text, summary):
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        summary["rejected_reasons"].append("Missing CSV header"); return summary
    # normalise fieldnames
    rows = list(reader)
    existing_hashes = {t.dedup_hash for t in db.query(Transaction).filter(Transaction.user_id == current.id).all() if t.dedup_hash}
    new_txns = []
    seen_in_file = set()
    for idx, raw in enumerate(rows, start=2):
        # extra columns: DictReader puts them under None key — ignore extras, don't crash
        row = { (k.strip().lower() if k else ""): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k }
        def get(*names):
            for n in names:
                if row.get(n): return row[n]
            return ""
        date_s = get("date"); amt_s = get("amount"); type_s = (get("type") or "expense").strip().lower()
        if not date_s or not amt_s:
            summary["rejected"] += 1; summary["rejected_reasons"].append(f"Row {idx}: missing required field(s) date/amount"); continue
        try:
            d = datetime.strptime(date_s, "%Y-%m-%d").date()
        except Exception:
            summary["rejected"] += 1; summary["rejected_reasons"].append(f"Row {idx}: invalid date '{date_s}'"); continue
        try:
            amt = Decimal(str(amt_s).replace(",", "").replace("₹","").strip())
            if not amt.is_finite() or amt < 0: raise InvalidOperation()
        except Exception:
            summary["rejected"] += 1; summary["rejected_reasons"].append(f"Row {idx}: invalid amount '{amt_s}'"); continue
        if type_s not in ("income","expense","transfer","refund"):
            summary["rejected"] += 1; summary["rejected_reasons"].append(f"Row {idx}: invalid type '{type_s}'"); continue
        merchant = get("merchant"); desc = get("description"); cat = get("category_name","category") or "Uncategorized"; cur = get("currency") or "INR"
        h = dedup_hash(current.id, d.isoformat(), str(amt), merchant, desc, type_s)
        if h in existing_hashes or h in seen_in_file:
            summary["duplicates"] += 1; continue
        seen_in_file.add(h)
        new_txns.append(Transaction(user_id=current.id, type=type_s, amount=amt, currency=cur, category_name=cat, merchant=merchant, description=desc, notes=get("notes"), date=d, is_recurring=get("is_recurring").lower() in ("true","1","yes"), dedup_hash=h))
        summary["accepted"] += 1
    # atomic insert of only validated, non-duplicate rows
    if new_txns:
        db.add_all(new_txns)
    db.add(AuditLog(user_id=current.id, action="csv_import", detail=str(summary)))
    db.commit()
    summary["errors"] = summary["rejected_reasons"]
    return summary



@router.post("/parse")
def parse_nl(data: dict, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Feature H: extract a transaction DRAFT from free text. Never writes
    to the database — creation happens only via POST /transactions after
    the user reviews and confirms the draft."""
    from app.nl_entry import parse_transaction_text
    from app.ml.categorization.model import suggest_category
    text = (data or {}).get("text", "")
    if not text or not str(text).strip():
        raise HTTPException(422, "text is required")
    draft = parse_transaction_text(str(text))
    try:
        sug = suggest_category(draft["description"], draft["merchant"])
        draft["category_name"] = sug.get("category") if isinstance(sug, dict) else None
        draft["category_confidence"] = sug.get("confidence") if isinstance(sug, dict) else None
    except Exception:
        draft["category_name"] = None
        draft["category_confidence"] = None
    if not draft["category_name"]:
        draft["category_name"] = "Uncategorized"
        if "category" not in draft["ambiguous_fields"]:
            draft["ambiguous_fields"].append("category")
    return draft


def _statement_rows_to_canonical(text: str):
    """Parse a bank/UPI statement CSV into canonical FinSight rows.
    Handles split Debit/Credit columns and UPI narration merchant
    extraction. Returns (rows, rejected_count)."""
    import re as _re
    from datetime import datetime as _dt
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], 0
    def norm(name):
        return _re.sub(r"[^a-z]", "", (name or "").lower())
    cols = {norm(fn): fn for fn in reader.fieldnames if fn}
    def pick(*cands):
        for cd in cands:
            if cd in cols:
                return cols[cd]
        return None
    date_c = pick("date", "txndate", "transactiondate", "valuedate", "postingdate")
    narr_c = pick("narration", "description", "particulars", "remarks", "transactiondetails", "details")
    debit_c = pick("debit", "withdrawal", "withdrawals", "debitamount", "dr")
    credit_c = pick("credit", "deposit", "deposits", "creditamount", "cr")
    amount_c = pick("amount", "txnamount", "transactionamount")
    if date_c is None or (debit_c is None and credit_c is None and amount_c is None):
        return None, 0  # not a recognisable statement layout
    date_fmts = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d-%b-%Y", "%d/%m/%y", "%m/%d/%Y", "%d.%m.%Y")
    rows, rejected = [], 0
    for raw in reader:
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
        ds = row.get(date_c, "")
        d = None
        for f in date_fmts:
            try:
                d = _dt.strptime(ds, f).date(); break
            except Exception:
                continue
        if d is None:
            rejected += 1; continue
        narration = row.get(narr_c, "") or ""
        def amt_of(col):
            if not col:
                return None
            v = (row.get(col) or "").replace(",", "").replace("₹", "").strip()
            if not v:
                return None
            try:
                x = Decimal(v)
                return x if x.is_finite() and x != 0 else None
            except Exception:
                return None
        debit, credit = amt_of(debit_c), amt_of(credit_c)
        if debit is not None:
            type_, amt = "expense", abs(debit)
        elif credit is not None:
            type_, amt = "income", abs(credit)
        else:
            a = amt_of(amount_c)
            if a is None:
                rejected += 1; continue
            marker = (narration + " " + " ".join(str(v) for v in row.values())).lower()
            type_, amt = ("income", abs(a)) if (" cr" in marker or a < 0 and "credit" in marker) else ("expense", abs(a))
        merchant = ""
        m = _re.search(r"(?:UPI|NEFT|IMPS|RTGS)/([^/]{2,40})/", narration, _re.IGNORECASE)
        if m:
            merchant = m.group(1).strip().title()
        rows.append({"date": d.isoformat(), "type": type_, "amount": str(amt), "currency": "INR",
                     "category_name": "", "merchant": merchant, "description": narration,
                     "notes": "statement import", "is_recurring": "false"})
    return rows, rejected


@router.post("/import-statement")
async def import_statement(file: UploadFile = File(...), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Feature I: bank/UPI statement CSV ingestion. Rows are validated and
    deduplicated through the exact same pipeline as the plain CSV import;
    an audit row (counts only, never contents) is stored."""
    content = await file.read()
    summary = {"accepted": 0, "rejected": 0, "duplicates": 0, "errors": [], "rejected_reasons": []}
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(422, f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(422, "Statement import currently supports CSV files (export your statement as CSV from your bank/UPI app)")
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        raise HTTPException(422, "File is not valid UTF-8 text")
    parsed = _statement_rows_to_canonical(text)
    if parsed[0] is None:
        raise HTTPException(422, "Could not recognise this statement layout (need a date column and debit/credit or amount columns)")
    rows, extra_rejected = parsed
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["date", "type", "amount", "currency", "category_name", "merchant", "description", "notes", "is_recurring"])
    from app.ml.categorization.model import suggest_category
    for r in rows:
        if not r["category_name"]:
            try:
                sug = suggest_category(r["description"], r["merchant"])
                r["category_name"] = sug.get("category") if isinstance(sug, dict) and sug.get("category") else "Uncategorized"
            except Exception:
                r["category_name"] = "Uncategorized"
        w.writerow([r["date"], r["type"], r["amount"], r["currency"], r["category_name"], r["merchant"], r["description"], r["notes"], r["is_recurring"]])
    summary = _import_csv_text(db, current, buf.getvalue(), summary)
    summary["rejected"] += extra_rejected
    rec = StatementImport(user_id=current.id, filename=file.filename or "", format_detected="bank_csv",
                          total_rows=len(rows) + extra_rejected, accepted=summary["accepted"],
                          duplicates=summary["duplicates"], rejected=summary["rejected"])
    db.add(rec); db.commit(); db.refresh(rec)
    summary["statement_import_id"] = rec.id
    summary["format_detected"] = "bank_csv"
    return summary


@router.post("/receipt-parse")
async def receipt_parse(file: UploadFile = File(...), current: User = Depends(get_current_user)):
    """Feature I: receipt OCR -> DRAFT fields (merchant/date/total). The
    image is processed in memory/temp storage and deleted immediately;
    nothing is written to the database. Requires the tesseract OCR engine
    on the server; without it the endpoint says so honestly (503)."""
    import os, re as _re, shutil, subprocess, tempfile
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(422, "Image exceeds the upload limit")
    if not shutil.which("tesseract"):
        raise HTTPException(503, "Receipt OCR engine (tesseract) is not installed on this server; enter the receipt manually or use quick-add")
    suffix = os.path.splitext(file.filename or "")[1] or ".png"
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(content); tmp = f.name
        proc = subprocess.run(["tesseract", tmp, "stdout", "--psm", "6"], capture_output=True, text=True, timeout=60)
        text = proc.stdout or ""
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    amounts = []
    for m in _re.finditer(r"([0-9][0-9,]*(?:\.[0-9]{2}))", text):
        try:
            amounts.append((float(m.group(1).replace(",", "")), m.group(1)))
        except ValueError:
            pass
    total = None
    for line in text.splitlines():
        if "total" in line.lower():
            m = _re.search(r"([0-9][0-9,]*(?:\.[0-9]{2}))", line)
            if m:
                total = float(m.group(1).replace(",", ""))
    if total is None and amounts:
        total = max(a[0] for a in amounts)
    dm = _re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text) or _re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", text)
    rdate = None
    if dm:
        g = [int(x) for x in dm.groups()]
        try:
            rdate = (datetime(g[0], g[1], g[2]) if g[0] > 1000 else datetime(g[2], g[1], g[0])).date().isoformat()
        except Exception:
            rdate = None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    merchant = lines[0].title() if lines else ""
    return {"merchant": merchant, "date": rdate, "amount": total, "currency": "INR",
            "type": "expense", "description": f"Receipt: {merchant}" if merchant else "Receipt",
            "ambiguous_fields": ([] if total else ["amount"]) + ([] if rdate else ["date"]),
            "requires_review": True,
            "note": "OCR draft — verify every field before confirming; the receipt image was not stored."}


@router.post("/{txn_id}/auto-categorize")
def auto_categorize(txn_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """Apply the ML/rule categoriser to one of the user's own transactions.
    Only applies confident suggestions (>= 0.50); otherwise reports the
    suggestion without changing data."""
    from app.ml.categorization.model import suggest_category
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == current.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    s = suggest_category(t.description or "", t.merchant or "")
    applied = False
    if s.get("confidence", 0) >= 0.5 and s.get("category") and s["category"] != "Uncategorized":
        t.category_name = s["category"]; db.commit(); db.refresh(t); applied = True
    return {**out(t), "suggestion": s, "applied": applied}

@router.get("/{txn_id}")
def get_one(txn_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == current.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    return out(t)

@router.put("/{txn_id}")
def update(txn_id: int, data: TransactionIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == current.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    for k, v in data.model_dump().items(): setattr(t, k, v)
    t.dedup_hash = dedup_hash(current.id, t.date.isoformat(), str(t.amount), t.merchant, t.description, t.type)
    db.commit(); db.refresh(t); return out(t)

@router.delete("/{txn_id}")
def delete(txn_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == txn_id, Transaction.user_id == current.id).first()
    if not t: raise HTTPException(404, "Transaction not found")
    db.delete(t); db.commit(); return {"detail": "Deleted"}
