/* Gov.ID dashboard: editable beneficial owners / officers (business records). */

(function () {
  "use strict";

  const list = document.getElementById("stk-list");
  const hidden = document.getElementById("shareholders_json");
  const addBtn = document.getElementById("stk-add");
  const empty = document.getElementById("stk-empty");
  if (!list || !hidden) return; // not a business dashboard

  function esc(v) {
    return String(v == null ? "" : v).replace(/"/g, "&quot;");
  }

  function rowTemplate(data) {
    data = data || {};
    const row = document.createElement("div");
    row.className = "stk-row";
    row.innerHTML =
      '<div class="stk-head">' +
      '  <span class="stk-title">Beneficial owner</span>' +
      '  <button type="button" class="stk-remove" title="Remove owner" aria-label="Remove owner">&times;</button>' +
      "</div>" +
      '<div class="field-grid">' +
      '  <div class="field-card"><label>First name</label>' +
      '    <input data-k="first_name" class="profile-input" value="' + esc(data.first_name) + '" /></div>' +
      '  <div class="field-card"><label>Last name</label>' +
      '    <input data-k="last_name" class="profile-input" value="' + esc(data.last_name) + '" /></div>' +
      '  <div class="field-card"><label><span class="sensitive-dot"></span> Date of birth</label>' +
      '    <input data-k="birthdate" type="date" class="profile-input" value="' + esc(data.birthdate) + '" /></div>' +
      '  <div class="field-card"><label>Ownership %</label>' +
      '    <input data-k="ownership_percent" type="number" min="0" max="100" step="0.01" class="profile-input" value="' + esc(data.ownership_percent) + '" /></div>' +
      '  <div class="field-card"><label><span class="sensitive-dot"></span> ID / passport no.</label>' +
      '    <input data-k="id_number" class="profile-input" value="' + esc(data.id_number) + '" /></div>' +
      '  <div class="field-card"><label>Role</label>' +
      '    <input data-k="title" class="profile-input" placeholder="e.g. Director" value="' + esc(data.title) + '" /></div>' +
      '  <div class="field-card span-2"><label>Address</label>' +
      '    <input data-k="address" class="profile-input" value="' + esc(data.address) + '" /></div>' +
      '  <div class="field-card"><label>Country (ISO alpha-2)</label>' +
      '    <input data-k="country" maxlength="2" class="profile-input" value="' + esc(data.country) + '" /></div>' +
      '  <div class="field-card stk-rep-card"><label>Role status</label>' +
      '    <label class="stk-rep"><input data-k="is_representative" type="checkbox"' + (data.is_representative ? " checked" : "") + ' /> <span>Authorised representative</span></label></div>' +
      "</div>";

    row.querySelector(".stk-remove").addEventListener("click", function () {
      row.remove();
      sync();
    });
    row.querySelectorAll("input").forEach(function (i) {
      i.addEventListener("input", sync);
      i.addEventListener("change", sync);
    });
    return row;
  }

  function sync() {
    const rows = [];
    list.querySelectorAll(".stk-row").forEach(function (row) {
      const obj = {};
      row.querySelectorAll("input[data-k]").forEach(function (i) {
        obj[i.dataset.k] = i.type === "checkbox" ? i.checked : i.value.trim();
      });
      // Owners are directors by convention in this demo; reps are directors too.
      obj.is_director = !!obj.is_representative;
      rows.push(obj);
    });
    hidden.value = JSON.stringify(rows);
    if (empty) empty.hidden = rows.length > 0;
  }

  if (addBtn) {
    addBtn.addEventListener("click", function () {
      list.appendChild(rowTemplate({}));
      sync();
    });
  }

  // Seed existing owners from the json_script payload.
  let seed = [];
  const dataEl = document.getElementById("stk-data");
  if (dataEl) {
    try {
      seed = JSON.parse(dataEl.textContent) || [];
    } catch (_) {
      seed = [];
    }
  }
  seed.forEach(function (s) {
    list.appendChild(rowTemplate(s));
  });
  sync();
})();
