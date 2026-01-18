# Bug Report: Dashboard Rendering Failure

> **Severity:** Critical  
> **Status:** Open  
> **Date:** 2026-01-18  
> **Component:** `frontend/index.html` - JobsTab Component

---

## Summary

The dashboard at `http://localhost:8000/dashboard` fails to render, displaying a completely blank page. This is caused by a **JSX syntax error** in the `JobsTab` component.

## Evidence

### Blank Dashboard State
![Blank Dashboard](/Users/mr.phariyawit/.gemini/antigravity/brain/341cecb0-f42b-4cf6-9997-3bd356555899/dashboard_initial_state_1768706548391.png)

### Investigation Recording
![Investigation Flow](/Users/mr.phariyawit/.gemini/antigravity/brain/341cecb0-f42b-4cf6-9997-3bd356555899/dashboard_bug_investigation_1768706489670.webp)

---

## Root Cause Analysis

### Problem
The `JobsTab` component contains **mismatched `<div>` tags** within the "Start Import" `Modal`. Specifically:

1. **Extra `</div>` after Browse button** (around line ~1340)
2. **Extra `</div>` before `</Modal>` closing tag** (around line ~1348)

### Why It Fails Silently
- The application uses **in-browser Babel transpilation** (`@babel/standalone`).
- When Babel encounters the syntax error, it fails to transpile the script.
- React never renders because the `App` component is never created.
- The `#root` element remains empty with just the "Loading..." fallback.

---

## Affected Code

**File:** `frontend/index.html` — `JobsTab` component, inside the Modal.

```diff
 <Modal isOpen={showImport} onClose={() => setShowImport(false)} title="Start Import">
   <div className="space-y-4">
     <div>
       <label className="block text-sm font-medium mb-1">Connection</label>
       <select ...>...</select>
     </div>
     <div>
       <label className="block text-sm font-medium mb-1">SharePoint Folder URL</label>
       <input ... />
       <button onClick={() => setShowBrowser(true)} ...>Browse</button>
     </div>
-  </div>                       <!-- EXTRA: Remove this -->
-  </div>                       <!-- EXTRA: Remove this -->
+  {/* Removed extra closing divs */}
   <button onClick={handleStartImport} ...>
     {importLoading ? <Spinner size="sm" /> : <Icons.Play />} Start Import
   </button>
-  </div>                       <!-- EXTRA: Remove this -->
+  {/* Removed extra closing div */}
   </Modal>
```

---

## Impact

| Area | Status |
|------|--------|
| **Frontend** | ❌ BROKEN — No UI renders |
| **Backend API** | ✅ Healthy — Returns 401 (expected without auth) |
| **Login Page** | ❌ Not visible (blocked by script error) |
| **All Tabs** | ❌ Untestable |
| **Import Flow** | ❌ Untestable |

---

## Recommended Fix

1. Open `frontend/index.html`
2. Locate the `JobsTab` component (search for `const JobsTab`)
3. Find the `<Modal isOpen={showImport}` section
4. Remove the extra `</div>` tags as shown in the diff above
5. Verify the Modal structure is:
   ```jsx
   <Modal>
     <div className="space-y-4">
       {/* form fields */}
     </div>
     <button>Start Import</button>
   </Modal>
   ```

---

## Console Logs (During Investigation)

```
Failed to load resource: 401 Unauthorized - /api/connections
Warning: CDN tailwindcss should not be used in production
Warning: In-browser Babel transformer for production is not recommended
```

> **Note:** The actual Babel syntax error doesn't always appear in logs due to how `@babel/standalone` handles failures.
