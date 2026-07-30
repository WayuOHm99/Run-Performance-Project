import * as ts from "typescript";
import { describe, expect, it } from "vitest";

import athleteScreenSource from "../../app/athlete/index.tsx?raw";
import queryKeysSource from "../../lib/query/keys.ts?raw";

import cardSource from "./check-in-card.tsx?raw";
import repositorySource from "./check-in-repository.ts?raw";
import choiceGroupSource from "./choice-group.tsx?raw";
import copySource from "./copy.ts?raw";
import domainSource from "./domain.ts?raw";
import errorsSource from "./errors.ts?raw";
import hydrationSource from "./hydration.ts?raw";
import localDateSource from "./local-date.ts?raw";
import queryOptionsSource from "./query-options.ts?raw";
import submissionSource from "./submission.ts?raw";
import hooksSource from "./use-daily-check-in.ts?raw";

/**
 * Structural guards for the rules that behaviour alone cannot pin down.
 *
 * Decision 10 forbids a persisted draft, an outbox, an automatic retry of a
 * health-bearing write, and any health value in a log; decision 2 forbids
 * deriving the local date through a UTC conversion; decision 7 forbids
 * `.upsert()`. Behavioural tests show the current code does none of these — see
 * `logging.test.ts` and `query-options.test.ts`. These guards stop a later edit
 * from quietly adding one.
 *
 * **The scan is AST-based**, using the `typescript` devDependency already in this
 * workspace. The previous version stripped comments with a regex, which treated
 * `//` inside a string literal as a comment marker: a line such as
 *
 *     const endpoint = "https://example.invalid"; console.error(payload);
 *
 * had everything after `https:` deleted, so the `console.error` was never seen.
 * Parsing removes that whole class of blind spot — a name is a violation only
 * when it appears as an identifier in the syntax tree, so a URL cannot hide code
 * and a comment mentioning a prohibited API cannot raise a false positive.
 *
 * Every diagnostic is a **file name plus a rule name**. Source text, identifiers
 * in context, and values never reach an assertion.
 *
 * `failure-probe.ts` is deliberately not in the scanned set: it is test support,
 * no runtime module imports it, and it never reaches a bundle. The import-closure
 * check below is what proves nothing the app actually loads was left out.
 */

type SourceFile = readonly [name: string, text: string];

/** Every TASK-013-owned file that can end up in the running app. */
const FEATURE_SOURCES: readonly SourceFile[] = [
  ["check-in-card.tsx", cardSource],
  ["check-in-repository.ts", repositorySource],
  ["choice-group.tsx", choiceGroupSource],
  ["copy.ts", copySource],
  ["domain.ts", domainSource],
  ["errors.ts", errorsSource],
  ["hydration.ts", hydrationSource],
  ["local-date.ts", localDateSource],
  ["query-options.ts", queryOptionsSource],
  ["submission.ts", submissionSource],
  ["use-daily-check-in.ts", hooksSource],
];

/** Owned files outside the feature directory. */
const OUTSIDE_SOURCES: readonly SourceFile[] = [
  ["app/athlete/index.tsx", athleteScreenSource],
  ["lib/query/keys.ts", queryKeysSource],
];

const SOURCES: readonly SourceFile[] = [...FEATURE_SOURCES, ...OUTSIDE_SOURCES];

type Violation = { readonly file: string; readonly rule: string };

function parse(name: string, text: string): ts.SourceFile {
  return ts.createSourceFile(
    name,
    text,
    ts.ScriptTarget.Latest,
    true,
    name.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
}

/**
 * Every identifier that appears in the syntax tree.
 *
 * Comments are not nodes, and a string literal's contents are a single token
 * rather than identifiers, so neither can contribute a name here.
 */
function identifiersIn(source: ts.SourceFile): ReadonlySet<string> {
  const names = new Set<string>();

  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node)) {
      names.add(node.text);
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return names;
}

/** Module specifiers of every import and export-from declaration. */
function importedModulesIn(source: ts.SourceFile): readonly string[] {
  const modules: string[] = [];

  const visit = (node: ts.Node): void => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier !== undefined &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      modules.push(node.moduleSpecifier.text);
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return modules;
}

/** Rule name → the identifiers that break it. */
const FORBIDDEN_IDENTIFIERS: readonly (readonly [
  rule: string,
  names: readonly string[],
])[] = [
  [
    "logging",
    [
      "console",
      "Sentry",
      "trackEvent",
      "logEvent",
      "captureException",
      "recordError",
      "reportError",
    ],
  ],
  [
    "persisted-draft-or-outbox",
    [
      "AsyncStorage",
      "SecureStore",
      "localStorage",
      "sessionStorage",
      "setItem",
      "getItem",
      "MMKV",
      "FileSystem",
      "createPersister",
      "persistQueryClient",
    ],
  ],
  [
    "background-work-or-notification",
    [
      "setInterval",
      "setTimeout",
      "requestIdleCallback",
      "BackgroundFetch",
      "TaskManager",
      "Notifications",
      "registerTaskAsync",
    ],
  ],
  [
    "utc-derived-date",
    [
      "toISOString",
      "toJSON",
      "toUTCString",
      "toLocaleDateString",
      "toLocaleString",
      "getUTCFullYear",
      "getUTCMonth",
      "getUTCDate",
      "getUTCDay",
      "UTC",
    ],
  ],
  ["upsert", ["upsert"]],
  ["optimistic-health-cache", ["onMutate", "setQueryData", "setQueriesData"]],
  ["identity-lookup-inside-the-feature", ["getUser", "getSession"]],
];

/** Rule name → the module specifiers that break it. */
const FORBIDDEN_MODULES: readonly (readonly [
  rule: string,
  modules: readonly string[],
])[] = [
  [
    "persisted-draft-or-outbox",
    [
      "@react-native-async-storage/async-storage",
      "expo-secure-store",
      "expo-file-system",
      "@tanstack/query-persist-client-core",
      "@tanstack/react-query-persist-client",
    ],
  ],
  [
    "background-work-or-notification",
    [
      "expo-notifications",
      "expo-background-fetch",
      "expo-background-task",
      "expo-task-manager",
    ],
  ],
];

/** Analyzes one source and returns its violations, by rule name only. */
export function violationsIn(name: string, text: string): readonly Violation[] {
  const source = parse(name, text);
  const identifiers = identifiersIn(source);
  const modules = new Set(importedModulesIn(source));
  const found: Violation[] = [];

  for (const [rule, names] of FORBIDDEN_IDENTIFIERS) {
    if (names.some((forbidden) => identifiers.has(forbidden))) {
      found.push({ file: name, rule });
    }
  }

  for (const [rule, specifiers] of FORBIDDEN_MODULES) {
    if (specifiers.some((forbidden) => modules.has(forbidden))) {
      found.push({ file: name, rule });
    }
  }

  return found;
}

describe("the TASK-013 source scan", () => {
  it("loaded every owned runtime file", () => {
    // Guards against the whole scan passing because it read nothing.
    const empty = SOURCES.filter(([, text]) => text.trim().length === 0).map(
      ([name]) => name,
    );

    expect(empty).toEqual([]);
    expect(FEATURE_SOURCES.length).toBe(11);
    expect(OUTSIDE_SOURCES.length).toBe(2);
  });

  it("covers every sibling module the scanned files import", () => {
    // Completeness guard. A new feature module that any scanned file imports must
    // be added to the list above, or this fails — which is what stops a future
    // module from escaping the scan entirely.
    const scanned = new Set(FEATURE_SOURCES.map(([name]) => name));
    const missing = new Set<string>();

    for (const [name, text] of SOURCES) {
      for (const specifier of importedModulesIn(parse(name, text))) {
        if (!specifier.startsWith("./")) {
          continue;
        }

        const base = specifier.slice(2);

        if (!scanned.has(`${base}.ts`) && !scanned.has(`${base}.tsx`)) {
          missing.add(base);
        }
      }
    }

    // Module base names only.
    expect([...missing].sort()).toEqual([]);
  });

  it("finds no violation in any owned runtime file", () => {
    const violations = SOURCES.flatMap(([name, text]) =>
      violationsIn(name, text),
    );

    // File names and rule names only.
    expect(violations).toEqual([]);
  });

  it("builds the local date from local calendar parts", () => {
    const identifiers = identifiersIn(parse("local-date.ts", localDateSource));

    expect(
      ["getFullYear", "getMonth", "getDate", "getTimezoneOffset"].filter(
        (accessor) => !identifiers.has(accessor),
      ),
    ).toEqual([]);
  });

  it("branches on a SQLSTATE rather than on error text", () => {
    const identifiers = identifiersIn(
      parse("check-in-repository.ts", repositorySource),
    );

    // Reading a server error's prose in control flow is what decision 8 forbids.
    expect(
      ["message", "details", "hint"].filter((field) => identifiers.has(field)),
    ).toEqual([]);
  });
});

/**
 * The scanner's own regression tests.
 *
 * A scanner that silently stops detecting things is worse than no scanner, so its
 * blind spots are tested directly against synthetic sources.
 */
describe("the scanner itself", () => {
  it("detects executable logging that follows a URL string literal", () => {
    // The exact case the previous regex scanner missed: everything after
    // `https:` looked like a line comment and was deleted.
    const synthetic = [
      'const endpoint = "https://example.invalid";',
      "console.error(payload);",
      "export const value = endpoint;",
    ].join("\n");

    expect(
      violationsIn("synthetic.ts", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["logging"]);
  });

  it("detects logging on the same line as a URL string literal", () => {
    const synthetic =
      'export const e = "https://example.invalid"; console.warn(e);';

    expect(
      violationsIn("synthetic.ts", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["logging"]);
  });

  it("detects logging hidden after a URL inside a template literal", () => {
    const synthetic = [
      "export const e = `https://example.invalid`;",
      "console.info(e);",
    ].join("\n");

    expect(
      violationsIn("synthetic.ts", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["logging"]);
  });

  it("does not flag a comment that names a prohibited API", () => {
    const synthetic = [
      "// Never use console.error here, and never call toISOString.",
      "/* AsyncStorage and setInterval are forbidden in this module. */",
      "export const safe = 1;",
    ].join("\n");

    expect(violationsIn("synthetic.ts", synthetic)).toEqual([]);
  });

  it("does not flag a prohibited API named only inside a string", () => {
    const synthetic =
      'export const label = "console.error and toISOString are forbidden";';

    expect(violationsIn("synthetic.ts", synthetic)).toEqual([]);
  });

  it("detects each rule from a synthetic breach", () => {
    const cases: readonly [string, string][] = [
      ["logging", "export const f = () => { console.log(1); };"],
      [
        "persisted-draft-or-outbox",
        'import AsyncStorage from "@react-native-async-storage/async-storage";\nexport const s = AsyncStorage;',
      ],
      [
        "background-work-or-notification",
        "export const f = () => { setTimeout(() => undefined, 1); };",
      ],
      [
        "utc-derived-date",
        "export const f = (d: Date) => d.toISOString().slice(0, 10);",
      ],
      [
        "upsert",
        "export const f = (c: { upsert: () => void }) => { c.upsert(); };",
      ],
      [
        "optimistic-health-cache",
        "export const options = { onMutate: () => undefined };",
      ],
      [
        "identity-lookup-inside-the-feature",
        "export const f = (a: { getUser: () => void }) => { a.getUser(); };",
      ],
    ];

    const undetected = cases
      .filter(
        ([rule, code]) =>
          !violationsIn("synthetic.ts", code).some(
            (violation) => violation.rule === rule,
          ),
      )
      .map(([rule]) => rule);

    // Rule names only.
    expect(undetected).toEqual([]);
  });

  it("detects a forbidden module even when imported under an alias", () => {
    const synthetic = [
      'import * as store from "expo-secure-store";',
      "export const s = store;",
    ].join("\n");

    expect(
      violationsIn("synthetic.ts", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["persisted-draft-or-outbox"]);
  });

  it("parses TSX without treating a generic as a JSX tag", () => {
    const synthetic = [
      "export const C = () => {",
      "  console.debug(1);",
      "  return null;",
      "};",
    ].join("\n");

    expect(
      violationsIn("synthetic.tsx", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["logging"]);
  });
});
