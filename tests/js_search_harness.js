const fs = require("fs");
const vm = require("vm");

function El(className, text, children) {
  this.classes = new Set(className ? [className] : []);
  this.dataset = { text: text || "" };
  this.children = children || [];
  this.open = false;
  this.parentElement = null;
  for (const child of this.children) child.parentElement = this;
  this.classList = {
    has: (name) => this.classes.has(name),
    add: (name) => this.classes.add(name),
    remove: (name) => this.classes.delete(name),
    toggle: (name, force) => {
      const on = force === undefined ? !this.classes.has(name) : !!force;
      if (on) this.classes.add(name);
      else this.classes.delete(name);
      return on;
    },
  };
  this.querySelectorAll = (selector) => queryList(descendants(this), selector);
}

function descendants(el) {
  const out = [];
  for (const child of el.children) {
    out.push(child, ...descendants(child));
  }
  return out;
}

function matches(el, selector) {
  let name = selector.trim();
  let hiddenFilter = false;
  if (name.endsWith(":not(.hidden)")) {
    hiddenFilter = true;
    name = name.slice(0, -":not(.hidden)".length);
  }
  if (!name.startsWith(".")) return false;
  const cls = name.slice(1);
  return el.classes.has(cls) && (!hiddenFilter || !el.classes.has("hidden"));
}

function queryList(elements, selector) {
  const parts = selector.split(",").map((s) => s.trim());
  return elements.filter((el) => parts.some((p) => matches(el, p)));
}

function queryAll(selector) {
  const all = [];
  for (const root of roots) all.push(root, ...descendants(root));
  return queryList(all, selector);
}

const fork = new El("fork", "");
const sub = new El("subagent", "");
const z = new El("thread", "zebra project", [fork, sub]);
const q = new El("thread", "quartz work", []);
const b = new El("group", "beta", [z]);
const a = new El("group", "alpha", [b, q]);
const roots = [a];

const controls = {
  search: { value: process.argv.length > 3 ? process.argv[3] : "", addEventListener() {} },
  "hide-subagents": { checked: true, addEventListener() {} },
  "hide-forks": { checked: false, addEventListener() {} },
  "expand-all": { addEventListener() {} },
  "collapse-all": { addEventListener() {} },
};

const document = {
  getElementById: (id) => controls[id],
  querySelectorAll: queryAll,
};
const window = {};

const code = fs.readFileSync(process.argv[2], "utf8");
const context = { document, window, Array, console };
vm.createContext(context);
vm.runInContext(code, context);
context.window.__apply();

console.log(JSON.stringify({
  a: a.classes.has("hidden"),
  b: b.classes.has("hidden"),
  z: z.classes.has("hidden"),
  q: q.classes.has("hidden"),
  fork: fork.classes.has("hidden"),
  sub: sub.classes.has("hidden"),
}));
