import * as ts from "typescript";
import { describe, expect, it } from "vitest";

import profileScreenSource from "../../app/profile.tsx?raw";
import queryKeysSource from "../../lib/query/keys.ts?raw";

import actionPlanSource from "./action-plan.ts?raw";
import copySource from "./copy.ts?raw";
import domainSource from "./domain.ts?raw";
import errorsSource from "./errors.ts?raw";
import queryOptionsSource from "./query-options.ts?raw";
import actionButtonSource from "./sharing-action-button.tsx?raw";
import repositorySource from "./sharing-repository.ts?raw";
import sectionSource from "./sharing-section.tsx?raw";
import hooksSource from "./use-check-in-sharing.ts?raw";

/**
 * Structural guards for the rules that behaviour alone cannot pin down.
 *
 * Decision 8 forbids an outbox, persistence, background work, and an automatic
 * retry; decision 7 forbids an optimistic cache write; decision 9 forbids reading
 * an identity anywhere but the auth provider; decision 2 forbids naming any
 * category other than `check_in`; and nothing in this feature may log. Behavioural
 * tests show the current code does none of these — see `logging.test.ts` and
 * `query-options.test.ts`. These guards stop a later edit from quietly adding one.
 *
 * **The scan is AST-based**, using the `typescript` devDependency already in this
 * workspace, so a name is a violation only when it appears as an identifier or a
 * string literal in the syntax tree. A comment mentioning a prohibited API cannot
 * raise a false positive, and a URL inside a string cannot hide code behind an
 * apparent `//` comment.
 *
 * Every diagnostic is a **file name plus a rule name**. Source text, identifiers in
 * context, and values never reach an assertion.
 *
 * `failure-probe.ts` is deliberately not in the scanned set: it is test support, no
 * runtime module imports it, and it never reaches a bundle. The import-closure check
 * below is what proves nothing the app actually loads was left out.
 */

type SourceFile = readonly [name: string, text: string];

/** Every TASK-014-owned file that can end up in the running app. */
const FEATURE_SOURCES: readonly SourceFile[] = [
  ["action-plan.ts", actionPlanSource],
  ["copy.ts", copySource],
  ["domain.ts", domainSource],
  ["errors.ts", errorsSource],
  ["query-options.ts", queryOptionsSource],
  ["sharing-action-button.tsx", actionButtonSource],
  ["sharing-repository.ts", repositorySource],
  ["sharing-section.tsx", sectionSource],
  ["use-check-in-sharing.ts", hooksSource],
];

/** Owned files outside the feature directory. */
const OUTSIDE_SOURCES: readonly SourceFile[] = [
  ["app/profile.tsx", profileScreenSource],
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
 * Comments are not nodes, and a string literal's contents are a single token rather
 * than identifiers, so neither can contribute a name here.
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

/** Every string and untemplated template literal in the syntax tree. */
function stringLiteralsIn(source: ts.SourceFile): ReadonlySet<string> {
  const values = new Set<string>();

  const visit = (node: ts.Node): void => {
    if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node)
    ) {
      values.add(node.text);
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return values;
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
    "persistence-or-outbox",
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
      "resumePausedMutations",
    ],
  ],
  ["optimistic-cache-write", ["onMutate", "setQueryData", "setQueriesData"]],
  ["identity-lookup-inside-the-feature", ["getUser", "getSession"]],
  // `authenticated` holds SELECT only on sharing_grants; the two RPCs are the only
  // client write path. A direct write would be refused, but it must not be written.
  ["direct-table-write", ["insert", "update", "upsert", "delete", "remove"]],
];

/** Rule name → the module specifiers that break it. */
const FORBIDDEN_MODULES: readonly (readonly [
  rule: string,
  modules: readonly string[],
])[] = [
  [
    "persistence-or-outbox",
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

/** Rule name → the string literals that break it. */
const FORBIDDEN_LITERALS: readonly (readonly [
  rule: string,
  values: readonly string[],
])[] = [
  // Decision 2: only check_in is supported. Naming another category anywhere in
  // runtime code is how that would start to drift.
  ["other-sharing-category", ["workout_summary", "sleep_summary"]],
];

/** Analyzes one source and returns its violations, by rule name only. */
export function violationsIn(name: string, text: string): readonly Violation[] {
  const source = parse(name, text);
  const identifiers = identifiersIn(source);
  const literals = stringLiteralsIn(source);
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

  for (const [rule, values] of FORBIDDEN_LITERALS) {
    if (values.some((forbidden) => literals.has(forbidden))) {
      found.push({ file: name, rule });
    }
  }

  return found;
}

describe("the TASK-014 source scan", () => {
  it("loaded every owned runtime file", () => {
    // Guards against the whole scan passing because it read nothing.
    const empty = SOURCES.filter(([, text]) => text.trim().length === 0).map(
      ([name]) => name,
    );

    expect(empty).toEqual([]);
    expect(FEATURE_SOURCES.length).toBe(9);
    expect(OUTSIDE_SOURCES.length).toBe(2);
  });

  it("covers every sibling module the scanned files import", () => {
    // Completeness guard. A new feature module that any scanned file imports must be
    // added to the list above, or this fails — which is what stops a future module
    // from escaping the scan entirely.
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

  it("names the category in exactly one runtime module", () => {
    // Every other module imports `CHECK_IN_CATEGORY`, so there is one place the
    // category could ever be changed and one place a review has to look.
    const naming = SOURCES.filter(([name, text]) =>
      stringLiteralsIn(parse(name, text)).has("check_in"),
    ).map(([name]) => name);

    expect(naming).toEqual(["domain.ts"]);
  });

  it("never reads a server error's prose in the repository", () => {
    const identifiers = identifiersIn(
      parse("sharing-repository.ts", repositorySource),
    );

    // Putting a server message, DETAIL, HINT, or cause into control flow is one
    // step away from putting it into the UI or a log.
    expect(
      ["message", "details", "hint", "cause"].filter((field) =>
        identifiers.has(field),
      ),
    ).toEqual([]);
  });

  it("declares networkMode and retry in the mutation options module", () => {
    const identifiers = identifiersIn(
      parse("query-options.ts", queryOptionsSource),
    );

    // Their *values* are asserted behaviourally; this only proves the options were
    // not silently dropped from the module altogether.
    expect(
      ["networkMode", "retry"].filter((option) => !identifiers.has(option)),
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
    // Everything after `https:` looks like a line comment to a regex scanner.
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

  it("does not flag a comment that names a prohibited API or category", () => {
    const synthetic = [
      "// Never use console.error here, and never call setQueryData.",
      "/* workout_summary and sleep_summary are out of scope. */",
      "export const safe = 1;",
    ].join("\n");

    expect(violationsIn("synthetic.ts", synthetic)).toEqual([]);
  });

  it("detects each rule from a synthetic breach", () => {
    const cases: readonly (readonly [string, string])[] = [
      ["logging", "export const f = () => { console.log(1); };"],
      [
        "persistence-or-outbox",
        'import AsyncStorage from "@react-native-async-storage/async-storage";\nexport const s = AsyncStorage;',
      ],
      [
        "background-work-or-notification",
        "export const f = () => { setTimeout(() => undefined, 1); };",
      ],
      [
        "optimistic-cache-write",
        "export const options = { onMutate: () => undefined };",
      ],
      [
        "identity-lookup-inside-the-feature",
        "export const f = (a: { getUser: () => void }) => { a.getUser(); };",
      ],
      [
        "direct-table-write",
        "export const f = (c: { insert: () => void }) => { c.insert(); };",
      ],
      ["other-sharing-category", 'export const category = "workout_summary";'],
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

  it("detects a forbidden category hidden in a template literal", () => {
    const synthetic = "export const c = `sleep_summary`;";

    expect(
      violationsIn("synthetic.ts", synthetic).map(
        (violation) => violation.rule,
      ),
    ).toEqual(["other-sharing-category"]);
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
    ).toEqual(["persistence-or-outbox"]);
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
