const assert = require("node:assert/strict");

const csv = require("../bambo_bot/web_static/financial-csv.js");

const trade = {
  invested_capital: 0.5000000000000001,
  long_offset_profit: 0.4000000000000001,
  money_values: {
    invested_capital: "0.5",
    long_offset_profit: "0.4",
  },
};

assert.equal(csv.money(trade, "invested_capital"), "0.5");
assert.equal(csv.money(trade, "long_offset_profit"), "0.4");
assert.equal(csv.money({invested_capital: 12.5}, "invested_capital"), 12.5);

const rendered = csv.render(
  [["سرمایه درگیر", (row) => csv.money(row, "invested_capital")]],
  [trade],
);
assert.equal(rendered, '"سرمایه درگیر"\r\n"0.5"');

const escaped = csv.render([["یادداشت", (row) => row.note]], [{note: 'الف "ب"'}]);
assert.equal(escaped, '"یادداشت"\r\n"الف ""ب"""');

console.log("financial CSV contract: PASS");
