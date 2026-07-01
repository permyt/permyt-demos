/* Government registry console: person/business toggle + shareholder rows. */

(function () {
  "use strict";

  const typeInput = document.getElementById("profile_type");
  const typeBtns = document.querySelectorAll(".type-btn");
  const fieldGroups = document.querySelectorAll(".type-fields");

  function setType(type) {
    typeInput.value = type;
    typeBtns.forEach((b) => b.classList.toggle("active", b.dataset.type === type));
    fieldGroups.forEach((g) => g.classList.toggle("hidden", g.dataset.fields !== type));
  }

  typeBtns.forEach((b) => b.addEventListener("click", () => setType(b.dataset.type)));

  // ── Shareholder rows ───────────────────────────────────────────────
  const list = document.getElementById("shareholders");
  const hidden = document.getElementById("shareholders_json");
  const addBtn = document.getElementById("add-shareholder");

  function rowTemplate() {
    const row = document.createElement("div");
    row.className = "shareholder-row";
    row.innerHTML =
      '<input data-k="first_name" placeholder="First name" />' +
      '<input data-k="last_name" placeholder="Last name" />' +
      '<input data-k="birthdate" type="date" />' +
      '<input data-k="ownership_percent" type="number" min="0" max="100" placeholder="% owned" />' +
      '<input data-k="id_number" placeholder="ID number" />' +
      '<label class="rep-check"><input data-k="is_representative" type="checkbox" /> Rep</label>' +
      '<button type="button" class="row-remove" title="Remove">&times;</button>';
    row.querySelector(".row-remove").addEventListener("click", function () {
      row.remove();
      sync();
    });
    row.querySelectorAll("input").forEach((i) => i.addEventListener("input", sync));
    return row;
  }

  function sync() {
    const rows = [];
    list.querySelectorAll(".shareholder-row").forEach(function (row) {
      const obj = {};
      row.querySelectorAll("input[data-k]").forEach(function (i) {
        obj[i.dataset.k] = i.type === "checkbox" ? i.checked : i.value;
      });
      // Owners are directors by convention in this demo; flag reps as directors too.
      obj.is_director = !!obj.is_representative;
      rows.push(obj);
    });
    hidden.value = JSON.stringify(rows);
  }

  if (addBtn) {
    addBtn.addEventListener("click", function () {
      list.appendChild(rowTemplate());
      sync();
    });
  }
})();
