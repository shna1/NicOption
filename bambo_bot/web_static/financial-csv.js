(function exposeFinancialCsv(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.NicOptionFinancialCsv = api;
})(typeof globalThis === "object" ? globalThis : this, () => {
  "use strict";

  function money(record, key) {
    const exact = record?.money_values?.[key];
    return exact !== undefined && exact !== null && exact !== ""
      ? exact
      : record?.[key];
  }

  function cell(value) {
    return `"${String(value ?? "").replaceAll('"', '""')}"`;
  }

  function render(columns, rows) {
    return [
      columns.map(([title]) => cell(title)).join(","),
      ...rows.map((row) => columns.map(([, read]) => cell(read(row))).join(",")),
    ].join("\r\n");
  }

  return Object.freeze({money, cell, render});
});
