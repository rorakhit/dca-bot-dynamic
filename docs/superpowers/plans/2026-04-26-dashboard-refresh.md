# Dashboard Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the desktop and mobile dashboards with a warm amber/gold palette, promote Claude's allocation reasoning to a first-class panel, and add a Plaid connection status panel showing the linked bank account name and masked number.

**Architecture:** Backend changes land first (plaid_store → plaid_client → plaid_routes → routes), each tested before the next. Dashboard restyling is last — pure HTML/CSS/JS within the two template strings in `dashboard.py`, no new endpoints needed once the backend is wired.

**Tech Stack:** Python/FastAPI backend, vanilla HTML/CSS/JS frontend (no build step), Chart.js 4.4.1, Plaid Python SDK, pytest.

---

## File Map

| File | What changes |
|---|---|
| `plaid_store.py` | Add `institution_name` + `account_mask` fields to `_DEFAULT`; add `set_account_info` / `get_account_info` |
| `plaid_client.py` | Add `get_account_info(access_token)` — calls Plaid `/item/get`, `/institutions/get_by_id`, `/accounts/get` |
| `plaid_routes.py` | Call `get_account_info` + `set_account_info` after token exchange in `plaid_callback` |
| `routes.py` | Add `plaid_institution` + `plaid_account_mask` to `/health` response |
| `dashboard.py` | Full restyling of `LANDING_HTML` + `DASHBOARD_HTML` |
| `tests/test_plaid_store.py` | New tests for `set_account_info` / `get_account_info` |
| `tests/test_plaid_client.py` | New test file — test `get_account_info` with mocked Plaid SDK |

---

## Task 1: Extend plaid_store with institution_name and account_mask

**Files:**
- Modify: `plaid_store.py`
- Test: `tests/test_plaid_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_plaid_store.py`:

```python
def test_get_account_info_returns_none_when_unset(temp_plaid_store):
    import plaid_store
    name, mask = plaid_store.get_account_info()
    assert name is None
    assert mask is None


def test_set_and_get_account_info(temp_plaid_store):
    import plaid_store
    plaid_store.set_account_info("Chase", "4521")
    name, mask = plaid_store.get_account_info()
    assert name == "Chase"
    assert mask == "4521"


def test_account_info_persists_across_reload(temp_plaid_store):
    import plaid_store
    plaid_store.set_account_info("SoFi", "7890")
    # Simulate reload by calling _load directly
    data = plaid_store._load()
    assert data["institution_name"] == "SoFi"
    assert data["account_mask"] == "7890"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/rorakhit/Documents/Projects/dca-bot-dynamic
pytest tests/test_plaid_store.py::test_get_account_info_returns_none_when_unset tests/test_plaid_store.py::test_set_and_get_account_info tests/test_plaid_store.py::test_account_info_persists_across_reload -v
```

Expected: FAIL — `AttributeError: module 'plaid_store' has no attribute 'get_account_info'`

- [ ] **Step 3: Implement the changes in plaid_store.py**

The `_DEFAULT` constant is at line 13. Add the two new fields:

```python
_DEFAULT = {
    "access_token": None,
    "cursor": None,
    "processed_ids": [],
    "action_tokens": {},
    "institution_name": None,
    "account_mask": None,
}
```

Then add the two new functions after the existing `get_access_token` / `set_access_token` pair:

```python
def set_account_info(institution_name: str, account_mask: str) -> None:
    data = _load()
    data["institution_name"] = institution_name
    data["account_mask"] = account_mask
    _save(data)


def get_account_info() -> tuple[str | None, str | None]:
    data = _load()
    return data.get("institution_name"), data.get("account_mask")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_plaid_store.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add plaid_store.py tests/test_plaid_store.py
git commit -m "feat: add institution_name and account_mask to plaid_store"
```

---

## Task 2: Add get_account_info() to plaid_client

**Files:**
- Modify: `plaid_client.py`
- Create: `tests/test_plaid_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_plaid_client.py`:

```python
from unittest.mock import MagicMock, patch


def test_get_account_info_returns_institution_and_mask():
    mock_item_response = MagicMock()
    mock_item_response.item.institution_id = "ins_3"

    mock_institution_response = MagicMock()
    mock_institution_response.institution.name = "Chase"

    mock_accounts_response = MagicMock()
    mock_account = MagicMock()
    mock_account.mask = "4521"
    mock_accounts_response.accounts = [mock_account]

    with patch("plaid_client.plaid_client") as mock_client:
        mock_client.item_get.return_value = mock_item_response
        mock_client.institutions_get_by_id.return_value = mock_institution_response
        mock_client.accounts_get.return_value = mock_accounts_response

        from plaid_client import get_account_info
        name, mask = get_account_info("access-sandbox-abc123")

    assert name == "Chase"
    assert mask == "4521"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_plaid_client.py::test_get_account_info_returns_institution_and_mask -v
```

Expected: FAIL — `ImportError: cannot import name 'get_account_info' from 'plaid_client'`

- [ ] **Step 3: Implement get_account_info in plaid_client.py**

Add imports at the top of `plaid_client.py` alongside existing imports:

```python
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
```

Add the function after `exchange_public_token`:

```python
def get_account_info(access_token: str) -> tuple[str, str]:
    """Return (institution_name, account_mask) for the linked account."""
    item_response = plaid_client.item_get(ItemGetRequest(access_token=access_token))
    institution_id = item_response.item.institution_id

    inst_response = plaid_client.institutions_get_by_id(
        InstitutionsGetByIdRequest(
            institution_id=institution_id,
            country_codes=[CountryCode("US")],
        )
    )
    institution_name = inst_response.institution.name

    accounts_response = plaid_client.accounts_get(
        AccountsGetRequest(access_token=access_token)
    )
    account_mask = accounts_response.accounts[0].mask

    return institution_name, account_mask
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_plaid_client.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plaid_client.py tests/test_plaid_client.py
git commit -m "feat: add get_account_info to plaid_client"
```

---

## Task 3: Persist account info after Plaid token exchange

**Files:**
- Modify: `plaid_routes.py:383-394`

No new tests needed here — this is a wiring step and the relevant units are already tested. The try/except ensures it's non-fatal.

- [ ] **Step 1: Update plaid_callback in plaid_routes.py**

The current `plaid_callback` body (lines 383–394) is:

```python
@router.post("/callback")
async def plaid_callback(request: Request):
    """Receives public_token from Plaid Link widget, exchanges for permanent access_token."""
    body = await request.json()
    public_token = body.get("public_token")
    if not public_token:
        raise HTTPException(status_code=400, detail="Missing public_token")
    access_token = exchange_public_token(public_token)
    set_access_token(access_token)
    write_audit_entry("plaid_linked", {})
    log.info("Plaid Link complete — access token stored")
    return {"status": "ok"}
```

Replace with:

```python
@router.post("/callback")
async def plaid_callback(request: Request):
    """Receives public_token from Plaid Link widget, exchanges for permanent access_token."""
    body = await request.json()
    public_token = body.get("public_token")
    if not public_token:
        raise HTTPException(status_code=400, detail="Missing public_token")
    access_token = exchange_public_token(public_token)
    set_access_token(access_token)
    try:
        institution_name, account_mask = get_account_info(access_token)
        set_account_info(institution_name, account_mask)
        log.info("Plaid account info stored: %s ••%s", institution_name, account_mask)
    except Exception as e:
        log.warning("Could not fetch Plaid account info (non-fatal): %s", e)
    write_audit_entry("plaid_linked", {})
    log.info("Plaid Link complete — access token stored")
    return {"status": "ok"}
```

- [ ] **Step 2: Add the missing imports to plaid_routes.py**

Find the block where `plaid_store` symbols are imported (around line 45–53). Add `get_account_info` and `set_account_info`:

```python
from plaid_store import (
    get_access_token,
    get_cursor,
    set_cursor,
    is_paycheck_processed,
    mark_paycheck_processed,
    set_access_token,
    get_account_info as get_stored_account_info,
    set_account_info,
)
```

And add the `get_account_info` import from `plaid_client`:

```python
from plaid_client import (
    create_link_token,
    exchange_public_token,
    sync_transactions,
    is_paycheck,
    verify_webhook,
    get_account_info,
)
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add plaid_routes.py
git commit -m "feat: persist Plaid institution name and account mask after link"
```

---

## Task 4: Surface Plaid account info in /health

**Files:**
- Modify: `routes.py:61-89`

- [ ] **Step 1: Add import to routes.py**

At the top of `routes.py`, find where `plaid_store` or other local modules are imported. Add:

```python
from plaid_store import get_account_info as get_plaid_account_info
```

- [ ] **Step 2: Update the health function**

The health function currently returns a `JSONResponse` at lines ~77–89. Add two fields:

```python
    plaid_institution, plaid_account_mask = get_plaid_account_info()

    return JSONResponse({
        "status": "ok" if not errors else "degraded",
        "errors": errors,
        "paper_trading": False,
        "strategy": "dynamic",
        "market_open": is_market_open(),
        "trading_day": is_trading_day(),
        "pending_approvals": len(pending_approvals),
        "next_contribution": next_run,
        "account_value_usd": account_value,
        "server_time_et": datetime.now(ET).isoformat(),
        "fund_lineup": list(BASE_TARGET_ALLOCATION.keys()),
        "plaid_institution": plaid_institution,
        "plaid_account_mask": plaid_account_mask,
    })
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add routes.py
git commit -m "feat: add plaid_institution and plaid_account_mask to /health response"
```

---

## Task 5: Dashboard — visual identity and nav (LANDING_HTML)

**Files:**
- Modify: `dashboard.py` (LANDING_HTML only in this task)

This task and tasks 6–9 are iterative HTML/CSS changes to `dashboard.py`. There are no automated tests for the HTML — verify visually by running the app.

- [ ] **Step 1: Update CSS custom properties and body background**

In `LANDING_HTML`, replace the `body` rule:

```css
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: #0a0805;
  color: #e2e8f0;
  min-height: 100vh;
}
```

- [ ] **Step 2: Update nav brand**

Replace the nav brand HTML block:

```html
<nav>
  <div class="nav-brand">
    <div class="icon">◈</div>
    <div>
      <div>DCA DYNAMIC</div>
      <div style="font-size:10px;font-weight:400;color:#78716c;letter-spacing:0.03em;margin-top:1px;">Automated wealth engine</div>
    </div>
  </div>
```

Update the `.nav-brand` icon CSS:

```css
.nav-brand .icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, #f59e0b, #b45309);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  box-shadow: 0 0 16px rgba(245,158,11,0.25);
}
```

- [ ] **Step 3: Update pill colours**

Replace the `.pill` colour variants:

```css
.pill.green  { background: rgba(52,211,153,0.12); color: #34d399; border-color: rgba(52,211,153,0.2); }
.pill.red    { background: rgba(248,113,113,0.12); color: #f87171; border-color: rgba(248,113,113,0.2); }
.pill.yellow { background: rgba(251,191,36,0.12);  color: #fbbf24; border-color: rgba(251,191,36,0.2); }
.pill.amber  { background: rgba(245,158,11,0.12);  color: #f59e0b; border-color: rgba(245,158,11,0.2); }
.pill.muted  { background: rgba(255,255,255,0.04); color: #64748b; border-color: rgba(255,255,255,0.06); }
```

- [ ] **Step 4: Update renderPortfolio status bar pills in JS**

In the `renderPortfolio` function, replace the `bar.innerHTML` line:

```js
bar.innerHTML = marketPill
  + '<span class="pill amber">Live</span>'
  + '<span class="pill amber">Plaid</span>'
  + nextPill;
```

- [ ] **Step 5: Commit**

```bash
git add dashboard.py
git commit -m "feat: update dashboard nav — amber palette, new branding, Plaid pill"
```

---

## Task 6: Dashboard — hero stats and P&L percentage (LANDING_HTML)

**Files:**
- Modify: `dashboard.py` (LANDING_HTML)

- [ ] **Step 1: Add amber and green hero card CSS classes**

Add after the existing `.stat-card` rules:

```css
.stat-card.amber {
  background: rgba(245,158,11,0.06);
  border-color: rgba(245,158,11,0.15);
}
.stat-card.green-card {
  background: rgba(52,211,153,0.05);
  border-color: rgba(52,211,153,0.15);
}
.stat-card .stat-value { color: #fef3c7; }
.stat-card .stat-percent {
  font-size: 11px;
  color: #34d399;
  margin-top: 2px;
}
```

- [ ] **Step 2: Update hero card HTML**

Replace the hero stat cards in the HTML:

```html
<div class="hero" id="hero">
  <div class="card stat-card amber"><div class="card-title">Portfolio value</div><div class="stat-value" id="s-total">—</div><div class="stat-sub">Total assets</div></div>
  <div class="card stat-card"><div class="card-title">Cash available</div><div class="stat-value" id="s-cash">—</div><div class="stat-sub">Uninvested</div></div>
  <div class="card stat-card"><div class="card-title">Invested</div><div class="stat-value" id="s-invested">—</div><div class="stat-sub">In positions</div></div>
  <div class="card stat-card" id="pl-card"><div class="card-title">Unrealised P&amp;L</div><div class="stat-value" id="s-pl">—</div><div class="stat-percent" id="s-pl-pct"></div></div>
</div>
```

- [ ] **Step 3: Update renderPortfolio JS to populate P&L percentage and green card class**

In `renderPortfolio`, after setting the P&L value, add:

```js
const plCard = document.getElementById('pl-card');
plCard.className = 'card stat-card ' + (pl >= 0 ? 'green-card' : '');

const costBasis = total - pl;
const plPct = costBasis > 0 ? (pl / costBasis * 100).toFixed(1) : '0.0';
const sPct = document.getElementById('s-pl-pct');
sPct.textContent = (pl >= 0 ? '+' : '') + plPct + '% all time';
sPct.style.color = pl >= 0 ? '#34d399' : '#f87171';
```

- [ ] **Step 4: Commit**

```bash
git add dashboard.py
git commit -m "feat: amber hero card, green P&L card, all-time percentage gain"
```

---

## Task 7: Dashboard — Claude reasoning callout + Plaid status panel (LANDING_HTML)

**Files:**
- Modify: `dashboard.py` (LANDING_HTML)

- [ ] **Step 1: Add CSS for the two new panels**

Add to the `<style>` block:

```css
/* ── Claude reasoning callout ── */
.reasoning-card {
  background: rgba(245,158,11,0.07);
  border: 1px solid rgba(245,158,11,0.18);
}
.reasoning-card .card-title { color: #92400e; }
.reasoning-text {
  color: #fcd34d;
  font-size: 13px;
  font-style: italic;
  line-height: 1.6;
}
.reasoning-meta { font-size: 10px; color: #78716c; margin-top: 8px; }

/* ── Plaid status panel ── */
.plaid-rows { display: flex; flex-direction: column; gap: 9px; margin-top: 4px; }
.plaid-row { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.plaid-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.plaid-dot.green  { background: #34d399; }
.plaid-dot.amber  { background: #f59e0b; }
.plaid-dot.red    { background: #f87171; }
.plaid-label { color: #94a3b8; }
.plaid-payday-label { font-size: 9px; color: #78716c; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 6px; }
.plaid-payday-value { font-size: 13px; font-weight: 700; color: #fef3c7; margin-top: 2px; }
```

- [ ] **Step 2: Add a new grid class for the 2fr/1fr row**

Add to the `<style>` block:

```css
.grid-plaid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
@media (max-width: 900px) {
  .grid-plaid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: Insert the new row HTML between hero and charts row**

After the closing `</div>` of the `.hero` div and before the `.grid-2` charts div, insert:

```html
<!-- ── Claude reasoning + Plaid status ── -->
<div class="grid-plaid">
  <div class="card reasoning-card">
    <div class="card-title">Claude's last allocation rationale</div>
    <div class="reasoning-text" id="reasoning-text">—</div>
    <div class="reasoning-meta" id="reasoning-meta"></div>
  </div>
  <div class="card">
    <div class="card-title">Paycheck automation</div>
    <div class="plaid-rows" id="plaid-rows">
      <div class="loading">…</div>
    </div>
    <div class="plaid-payday-label">Next expected payday</div>
    <div class="plaid-payday-value" id="plaid-payday">—</div>
  </div>
</div>
```

- [ ] **Step 4: Add renderReasoning and renderPlaid JS functions**

Add these functions before `loadAll`:

```js
function renderReasoning(entries) {
  const latest = entries.find(e => e.event === 'dynamic_allocation_proposed');
  const textEl = document.getElementById('reasoning-text');
  const metaEl = document.getElementById('reasoning-meta');
  if (!latest) {
    textEl.textContent = 'No allocation reasoning yet — appears after the first contribution cycle.';
    textEl.style.fontStyle = 'normal';
    textEl.style.color = '#475569';
    metaEl.textContent = '';
    return;
  }
  const reason = latest.allocation_reasoning || latest.reasoning || '';
  textEl.textContent = reason ? `"${reason}"` : '(No reasoning recorded for this cycle.)';
  metaEl.textContent = fmtTs(latest.timestamp) + ' · Dynamic strategy';
}

function renderPlaid(health) {
  const connected = health.plaid_institution != null;
  const institution = health.plaid_institution || '';
  const mask = health.plaid_account_mask || '';
  const rows = document.getElementById('plaid-rows');

  if (connected) {
    rows.innerHTML = `
      <div class="plaid-row">
        <div class="plaid-dot green"></div>
        <span class="plaid-label">${institution} ••${mask} connected</span>
      </div>
      <div class="plaid-row">
        <div class="plaid-dot amber"></div>
        <span class="plaid-label">Watching for deposit</span>
      </div>`;
  } else {
    rows.innerHTML = `
      <div class="plaid-row">
        <div class="plaid-dot red"></div>
        <span class="plaid-label">No account linked</span>
      </div>`;
  }

  const paydayEl = document.getElementById('plaid-payday');
  if (health.next_contribution && health.next_contribution !== 'event_driven') {
    paydayEl.textContent = fmtTs(health.next_contribution);
  } else {
    paydayEl.textContent = 'On next paycheck';
  }
}
```

- [ ] **Step 5: Wire up the new functions in loadAll**

In `loadAll`, after calling `renderPortfolio` and `renderHistory`, add:

```js
renderReasoning(audit);
renderPlaid(health);
```

- [ ] **Step 6: Commit**

```bash
git add dashboard.py
git commit -m "feat: add Claude reasoning callout and Plaid status panel to desktop dashboard"
```

---

## Task 8: Dashboard — chart and allocation colours (LANDING_HTML)

**Files:**
- Modify: `dashboard.py` (LANDING_HTML)

- [ ] **Step 1: Update COLORS constant in JS**

Replace:

```js
const COLORS = {
  VTI:  '#f59e0b', VXUS: '#34d399', AVUV: '#60a5fa', BND: '#f87171',
  default: ['#f59e0b','#34d399','#60a5fa','#f87171','#d97706','#fbbf24'],
};
```

- [ ] **Step 2: Update value chart gradient in mkValueChart**

Replace the gradient colour stops:

```js
grad.addColorStop(0, 'rgba(245,158,11,0.25)');
grad.addColorStop(1, 'rgba(245,158,11,0)');
```

And replace the dataset borderColor:

```js
borderColor: '#f59e0b', backgroundColor: grad,
```

And replace pointBackgroundColor:

```js
pointBackgroundColor: '#f59e0b',
```

- [ ] **Step 3: Commit**

```bash
git add dashboard.py
git commit -m "feat: update chart and allocation colours to amber palette"
```

---

## Task 9: Dashboard — contribution history accent colour (LANDING_HTML)

**Files:**
- Modify: `dashboard.py` (LANDING_HTML)

- [ ] **Step 1: Update contrib-alloc span colour in CSS**

Replace:

```css
.contrib-alloc span { color: #f59e0b; font-weight: 600; }
```

- [ ] **Step 2: Commit**

```bash
git add dashboard.py
git commit -m "feat: amber accent on contribution allocation amounts"
```

---

## Task 10: Mobile dashboard (DASHBOARD_HTML) — full parity

**Files:**
- Modify: `dashboard.py` (DASHBOARD_HTML only)

Apply all the same changes from Tasks 5–9 to `DASHBOARD_HTML`, plus the mobile-specific layout for the two new panels.

- [ ] **Step 1: Update body background**

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0a0805;
  color: #e2e8f0;
  min-height: 100vh;
  padding: 16px;
}
```

- [ ] **Step 2: Update mobile header HTML**

Replace the `<header>` block:

```html
<header>
  <div style="display:flex;align-items:center;gap:9px;">
    <div style="width:30px;height:30px;background:linear-gradient(135deg,#f59e0b,#b45309);border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;">◈</div>
    <div>
      <div style="color:#fef3c7;font-size:14px;font-weight:700;letter-spacing:0.04em;">DCA DYNAMIC</div>
      <div style="color:#78716c;font-size:9px;letter-spacing:0.03em;">Automated wealth engine</div>
    </div>
  </div>
  <button id="refresh-btn" onclick="loadAll()">↻ Refresh</button>
</header>
```

- [ ] **Step 3: Update mobile status bar pills**

In the mobile `renderPortfolio` JS, replace `bar.innerHTML`:

```js
bar.innerHTML = marketPill
  + '<span class="pill" style="background:rgba(245,158,11,0.12);color:#f59e0b;border:1px solid rgba(245,158,11,0.2);">Live</span>'
  + '<span class="pill" style="background:rgba(245,158,11,0.12);color:#f59e0b;border:1px solid rgba(245,158,11,0.2);">Plaid</span>'
  + nextPill;
```

- [ ] **Step 4: Add mobile Claude reasoning + Plaid panel CSS**

Add to the mobile `<style>` block:

```css
.reasoning-card {
  background: rgba(245,158,11,0.07);
  border: 1px solid rgba(245,158,11,0.18);
}
.reasoning-text {
  color: #fcd34d;
  font-size: 12px;
  font-style: italic;
  line-height: 1.6;
}
.reasoning-meta { font-size: 10px; color: #78716c; margin-top: 6px; }
.plaid-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.plaid-row { display: flex; align-items: center; gap: 7px; font-size: 11px; }
.plaid-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.plaid-dot.green { background: #34d399; }
.plaid-dot.amber { background: #f59e0b; }
.plaid-dot.red   { background: #f87171; }
.plaid-label { color: #94a3b8; }
.plaid-payday-label { font-size: 9px; color: #78716c; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 6px; }
.plaid-payday-value { font-size: 13px; font-weight: 700; color: #fef3c7; margin-top: 2px; }
```

- [ ] **Step 5: Insert the two new cards in the mobile HTML**

Insert after the portfolio value card and before the allocation card:

```html
<!-- ── Claude reasoning ── -->
<div class="card reasoning-card">
  <div class="card-title" style="color:#92400e;">Claude's last allocation rationale</div>
  <div class="reasoning-text" id="reasoning-text">—</div>
  <div class="reasoning-meta" id="reasoning-meta"></div>
</div>

<!-- ── Plaid status ── -->
<div class="card">
  <div class="card-title">Paycheck automation</div>
  <div class="plaid-rows" id="plaid-rows"><div class="loading">…</div></div>
  <div class="plaid-payday-label">Next expected payday</div>
  <div class="plaid-payday-value" id="plaid-payday">—</div>
</div>
```

- [ ] **Step 6: Add renderReasoning and renderPlaid to mobile JS, wire into loadAll**

Add before `loadAll` in the mobile JS:

```js
function renderReasoning(entries) {
  const latest = entries.find(e => e.event === 'dynamic_allocation_proposed');
  const textEl = document.getElementById('reasoning-text');
  const metaEl = document.getElementById('reasoning-meta');
  if (!latest) {
    textEl.textContent = 'No allocation reasoning yet — appears after the first contribution cycle.';
    textEl.style.fontStyle = 'normal';
    textEl.style.color = '#475569';
    metaEl.textContent = '';
    return;
  }
  const reason = latest.allocation_reasoning || latest.reasoning || '';
  textEl.textContent = reason ? `"${reason}"` : '(No reasoning recorded for this cycle.)';
  metaEl.textContent = fmtTs(latest.timestamp) + ' · Dynamic strategy';
}

function renderPlaid(health) {
  const connected = health.plaid_institution != null;
  const institution = health.plaid_institution || '';
  const mask = health.plaid_account_mask || '';
  const rows = document.getElementById('plaid-rows');
  if (connected) {
    rows.innerHTML = `
      <div class="plaid-row"><div class="plaid-dot green"></div><span class="plaid-label">${institution} ••${mask} connected</span></div>
      <div class="plaid-row"><div class="plaid-dot amber"></div><span class="plaid-label">Watching for deposit</span></div>`;
  } else {
    rows.innerHTML = `<div class="plaid-row"><div class="plaid-dot red"></div><span class="plaid-label">No account linked</span></div>`;
  }
  const paydayEl = document.getElementById('plaid-payday');
  paydayEl.textContent = (health.next_contribution && health.next_contribution !== 'event_driven')
    ? fmtTs(health.next_contribution) : 'On next paycheck';
}
```

In the mobile `loadAll`, after `renderPortfolio` and `renderHistory`:

```js
renderReasoning(audit);
renderPlaid(health);
```

- [ ] **Step 7: Update mobile COLORS, chart gradient, and contrib-alloc accent**

Replace `COLORS` in mobile JS:

```js
const COLORS = {
  VTI:  '#f59e0b', VXUS: '#34d399', AVUV: '#60a5fa', BND: '#f87171',
  default: ['#f59e0b','#34d399','#60a5fa','#f87171','#d97706','#fbbf24'],
};
```

In mobile `mkValueChart`, update gradient and line colour:

```js
grad.addColorStop(0, 'rgba(245,158,11,0.3)');
grad.addColorStop(1, 'rgba(245,158,11,0)');
// borderColor: '#f59e0b'
```

In mobile CSS, update `.contrib-alloc span`:

```css
.contrib-alloc span { color: #f59e0b; font-weight: 600; }
```

- [ ] **Step 8: Update mobile P&L card with green glow and percentage**

Add CSS:

```css
.stat .value.amber { color: #fef3c7; }
.stat-card-amber { background: rgba(245,158,11,0.06); border-color: rgba(245,158,11,0.15); }
.stat-card-green { background: rgba(52,211,153,0.05); border-color: rgba(52,211,153,0.15); }
```

In mobile `renderPortfolio` JS, update the stats innerHTML to wrap portfolio value in an amber card and P&L in a green card when positive, and include percentage:

```js
const pl = Object.values(p.holdings).reduce((s, h) => s + h.unrealized_pl, 0);
const plClass = pl >= 0 ? 'green' : 'red';
const costBasis = p.total_value - pl;
const plPct = costBasis > 0 ? (pl / costBasis * 100).toFixed(1) : '0.0';
const plCardClass = pl >= 0 ? 'stat-card-green' : '';

document.getElementById('stats').innerHTML = `
  <div class="stat stat-card-amber" style="background:rgba(245,158,11,0.06);border:1px solid rgba(245,158,11,0.15);border-radius:10px;padding:10px;">
    <div class="label">Total value</div>
    <div class="value" style="color:#fef3c7;">${fmt(p.total_value)}</div>
  </div>
  <div class="stat">
    <div class="label">Cash available</div>
    <div class="value">${fmt(p.cash_available)}</div>
  </div>
  <div class="stat" style="margin-top:8px">
    <div class="label">Invested</div>
    <div class="value">${fmt(p.total_value - p.cash_available)}</div>
  </div>
  <div class="stat ${plCardClass}" style="margin-top:8px;${pl >= 0 ? 'background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.15);border-radius:10px;padding:10px;' : ''}">
    <div class="label">Unrealised P&L</div>
    <div class="value ${plClass}">${fmt(pl)}</div>
    <div style="font-size:10px;color:#34d399;margin-top:2px;">${pl >= 0 ? '+' : ''}${plPct}% all time</div>
  </div>
`;
```

- [ ] **Step 9: Run all tests one final time**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 10: Commit**

```bash
git add dashboard.py
git commit -m "feat: apply full dashboard refresh to mobile template"
```

---

## Self-Review Notes

- **Spec coverage:** All sections covered — visual identity (Tasks 5–10), nav (Task 5), hero stats (Task 6), Claude callout (Task 7), Plaid panel (Tasks 1–4, 7), charts (Task 8), contribution colours (Task 9), mobile (Task 10).
- **Backend → frontend dependency:** Tasks 1–4 must complete before Task 7 (Plaid panel reads `plaid_institution` / `plaid_account_mask` from `/health`). All other tasks are independent.
- **next_contribution field:** The health endpoint returns `"event_driven"` as a string (not a date) post-Plaid integration. `renderPlaid` handles this with the fallback `"On next paycheck"`. The `nextPill` in the nav uses `fmtTs` — guarded by the `health.next_contribution` truthiness check; `"event_driven"` will pass `new Date("event_driven")` which is Invalid Date. Fix: in `renderPortfolio`, change the nextPill logic to:

```js
const nextPill = (health.next_contribution && health.next_contribution !== 'event_driven')
  ? `<span class="pill muted">Next run: ${fmtTs(health.next_contribution)}</span>` : '';
```

Apply this fix in both `LANDING_HTML` and `DASHBOARD_HTML` in Task 5 / Task 10.
