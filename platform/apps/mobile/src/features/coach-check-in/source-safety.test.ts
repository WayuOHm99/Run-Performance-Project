import * as ts from "typescript";
import { describe, expect, it } from "vitest";

import coachScreenSource from "../../app/coach/index.tsx?raw";
import queryKeysSource from "../../lib/query/keys.ts?raw";

import athleteCardSource from "./athlete-check-in-card.tsx?raw";
import repositorySource from "./coach-review-repository.ts?raw";
import sectionSource from "./coach-check-in-section.tsx?raw";
import copySource from "./copy.ts?raw";
import domainSource from "./domain.ts?raw";
import errorsSource from "./errors.ts?raw";
import queryOptionsSource from "./query-options.ts?raw";
import hookSource from "./use-coach-check-in-review.ts?raw";
import viewStateSource from "./view-state.ts?raw";

/**
 * Structural guards for the rules that behaviour alone cannot pin down.
 *
 * Decision 8 forbids polling, Realtime, persistence, background work, and an
 * automatic retry; decision 10 forbids every write path; decision 9 forbids reading
 * an identity anywhere but the auth provider and forbids displaying a raw
 * identifier; decision 5 forbids `select("*")` and forbids converting the recorded
 * date through UTC; and nothing in this feature may log. Behavioural tests show the
 * current code does none of these — see `logging.test.ts`, `query-options.test.ts`,
 * and `coach-review-repository.test.ts`. These guards stop a later edit from quietly
 * adding one.
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
 * `failure-probe.ts` and `test-fixtures.ts` are deliberately not in the scanned
 * set: both are test support, no runtime module imports either, and neither reaches
 * a bundle. The import-closure check below is what proves nothing the app actually
 * loads was left out.
 */

type SourceFile = readonly [name: string, text: string];

/** Every TASK-016-owned file that can end up in the running app. */
const FEATURE_SOURCES: readonly SourceFile[] = [
  ["athlete-check-in-card.tsx", athleteCardSource],
  ["coach-check-in-section.tsx", sectionSource],
  ["coach-review-repository.ts", repositorySource],
  ["copy.ts", copySource],
  ["domain.ts", domainSource],
  ["errors.ts", errorsSource],
  ["query-options.ts", queryOptionsSource],
  ["use-coach-check-in-review.ts", hookSource],
  ["view-state.ts", viewStateSource],
];

/** Owned files outside the feature directory. */
const OUTSIDE_SOURCES: readonly SourceFile[] = [
  ["app/coach/index.tsx", coachScreenSource],
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

/** How many times a JSX element with the given tag name appears. */
function jsxElementCount(source: ts.SourceFile, tagName: string): number {
  let found = 0;

  const visit = (node: ts.Node): void => {
    if (
      (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) &&
      ts.isIdentifier(node.tagName) &&
      node.tagName.text === tagName
    ) {
      found += 1;
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return found;
}

/** How many JSX `key` attributes call the given function. */
function jsxKeysCalling(source: ts.SourceFile, functionName: string): number {
  let found = 0;

  const callsFunction = (node: ts.Node): boolean => {
    let calls = false;

    const walk = (inner: ts.Node): void => {
      if (
        ts.isCallExpression(inner) &&
        ts.isIdentifier(inner.expression) &&
        inner.expression.text === functionName
      ) {
        calls = true;
      }

      ts.forEachChild(inner, walk);
    };

    walk(node);

    return calls;
  };

  const visit = (node: ts.Node): void => {
    if (
      ts.isJsxAttribute(node) &&
      ts.isIdentifier(node.name) &&
      node.name.text === "key" &&
      node.initializer !== undefined &&
      callsFunction(node.initializer)
    ) {
      found += 1;
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return found;
}

/**
 * Every property name read off one object identifier.
 *
 * Counts both `obj.prop` and `const { prop } = obj`. Covering the destructuring
 * form matters: without it, changing `athlete.checkIn` to a destructure would empty
 * the result and the "never renders an identifier" assertion would pass vacuously.
 */
function propertiesReadFrom(
  source: ts.SourceFile,
  objectName: string,
): ReadonlySet<string> {
  const properties = new Set<string>();

  const visit = (node: ts.Node): void => {
    if (
      ts.isPropertyAccessExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === objectName
    ) {
      properties.add(node.name.text);
    }

    if (
      ts.isVariableDeclaration(node) &&
      node.initializer !== undefined &&
      ts.isIdentifier(node.initializer) &&
      node.initializer.text === objectName &&
      ts.isObjectBindingPattern(node.name)
    ) {
      for (const element of node.name.elements) {
        const source_ = element.propertyName ?? element.name;

        if (ts.isIdentifier(source_)) {
          properties.add(source_.text);
        }
      }
    }

    ts.forEachChild(node, visit);
  };

  ts.forEachChild(source, visit);

  return properties;
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
  // Decision 8: freshness comes from mounting and a deliberate press, never from a
  // timer or a live subscription pushing health data at an unattended device.
  [
    "polling-or-realtime",
    [
      "refetchInterval",
      "refetchIntervalInBackground",
      "channel",
      "removeChannel",
      "subscribe",
      "realtime",
    ],
  ],
  // Decision 10: the coach side is read-only. There is no mutation of any kind.
  [
    "write-path",
    [
      "insert",
      "update",
      "upsert",
      "delete",
      "remove",
      "rpc",
      "useMutation",
      "mutationFn",
      "onMutate",
    ],
  ],
  ["optimistic-cache-write", ["setQueryData", "setQueriesData"]],
  ["identity-lookup-inside-the-feature", ["getUser", "getSession"]],
  // Decision 5: the athlete's recorded civil date is never converted through UTC.
  [
    "utc-date-conversion",
    [
      "toISOString",
      "toUTCString",
      "getUTCFullYear",
      "getUTCMonth",
      "getUTCDate",
      "toLocaleDateString",
    ],
  ],
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
  // Decision 3: only check_in consent is read. Naming another category anywhere in
  // runtime code is how that would start to drift.
  ["other-sharing-category", ["workout_summary", "sleep_summary"]],
  // Decision 5 and 6: explicit columns only, and no column the screen does not
  // display. A `*` select would hand this client rows it promised never to receive.
  ["wildcard-or-unused-column", ["*"]],
];

/**
 * Rule name → literal *fragments* that break it.
 *
 * Exact matching is not enough here. A select list is one literal holding many
 * column names, so `"id, daily_check_ins(*)"` and `"id, created_at"` both breach
 * decision 5 while equalling neither `"*"` nor `"created_at"`. Kept separate from
 * the exact list because substring matching is blunt, so only fragments that cannot
 * appear innocently in this feature's runtime code are listed here.
 */
const FORBIDDEN_LITERAL_FRAGMENTS: readonly (readonly [
  rule: string,
  fragments: readonly string[],
])[] = [
  [
    "wildcard-or-unused-column",
    ["(*)", "select(*", ", *", "* ,", "created_at", "updated_at"],
  ],
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

  for (const [rule, fragments] of FORBIDDEN_LITERAL_FRAGMENTS) {
    const breached = [...literals].some((literal) =>
      fragments.some((fragment) => literal.includes(fragment)),
    );

    if (breached && !found.some((violation) => violation.rule === rule)) {
      found.push({ file: name, rule });
    }
  }

  return found;
}

describe("the TASK-016 source scan", () => {
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

  it("names the sharing category in exactly one runtime module", () => {
    // Every other module imports `CHECK_IN_CATEGORY`, so there is one place the
    // category could ever be changed and one place a review has to look.
    const naming = SOURCES.filter(([name, text]) =>
      stringLiteralsIn(parse(name, text)).has("check_in"),
    ).map(([name]) => name);

    expect(naming).toEqual(["domain.ts"]);
  });

  it("selects exactly the approved columns, and only in the repository", () => {
    const selects = SOURCES.filter(([name, text]) =>
      [...stringLiteralsIn(parse(name, text))].some((literal) =>
        literal.includes("daily_check_ins("),
      ),
    ).map(([name]) => name);

    expect(selects).toEqual(["coach-review-repository.ts"]);

    const literals = stringLiteralsIn(
      parse("coach-review-repository.ts", repositorySource),
    );

    // The three select lists, pinned exactly. Adding a column is a test change.
    expect(literals.has("team_id, role, status, teams(name)")).toBe(true);
    expect(literals.has("team_id, athlete_profile_id, data_category")).toBe(
      true,
    );
    expect(
      literals.has(
        "id, display_name, daily_check_ins(check_in_date, rpe, overall_feeling, pain_status)",
      ),
    ).toBe(true);
  });

  it("orders and limits the embedded relation in the repository", () => {
    const identifiers = identifiersIn(
      parse("coach-review-repository.ts", repositorySource),
    );

    // Their *values* are asserted behaviourally against the client double; this
    // proves the calls were not silently dropped from the module altogether.
    expect(
      ["order", "limit", "referencedTable", "ascending"].filter(
        (name) => !identifiers.has(name),
      ),
    ).toEqual([]);
  });

  it("never reads a server error's prose in the repository", () => {
    const identifiers = identifiersIn(
      parse("coach-review-repository.ts", repositorySource),
    );

    // Putting a server message, DETAIL, HINT, or cause into control flow is one
    // step away from putting it into the UI or a log.
    expect(
      ["message", "details", "hint", "cause"].filter((field) =>
        identifiers.has(field),
      ),
    ).toEqual([]);
  });

  it("declares every cache override in the options module", () => {
    const identifiers = identifiersIn(
      parse("query-options.ts", queryOptionsSource),
    );

    expect(
      ["staleTime", "gcTime", "retry", "networkMode", "refetchOnMount"].filter(
        (option) => !identifiers.has(option),
      ),
    ).toEqual([]);
  });

  it("keys the hook-owning subtree by the verified identity", () => {
    // The identity boundary is a `key` prop, which cannot be exercised without a
    // component renderer this task may not add. Structurally: exactly one JSX `key`
    // in the section is derived from `coachReviewIdentityBoundaryKey`. Deleting it —
    // which is what reusing the observer across accounts looks like — fails here.
    const source = parse("coach-check-in-section.tsx", sectionSource);

    expect(jsxKeysCalling(source, "coachReviewIdentityBoundaryKey")).toBe(1);
    // And the identity it keys on comes from the auth provider, not a prop.
    expect(identifiersIn(source).has("useAuth")).toBe(true);
  });

  it("renders nothing from query state except through the view derivation", () => {
    // `data`, `isFetching`, and `isError` must arrive through
    // `readCoachReviewView`, which is the function the refresh-hiding regression
    // asserts against a real observer result. `error` is passed straight to the
    // sanitizer and `refetch` starts a reload; nothing else is allowed.
    const accessed = propertiesReadFrom(
      parse("coach-check-in-section.tsx", sectionSource),
      "query",
    );

    // Property names only.
    expect([...accessed].sort()).toEqual(["error", "refetch"]);
  });

  it("never renders an identifier in the athlete card", () => {
    // Decision 9 forbids displaying a raw UUID. `athleteProfileId` is a join and
    // reconciliation key; the card must not read it at all.
    const accessed = propertiesReadFrom(
      parse("athlete-check-in-card.tsx", athleteCardSource),
      "athlete",
    );

    expect([...accessed].sort()).toEqual(["athleteName", "checkIn"]);
  });

  it("keeps the two untouched placeholders on the coach screen", () => {
    // Decision 1: only the Team placeholder is replaced. The monitoring-flags and
    // training-plan cards stay, and no route or tab is added.
    const source = parse("app/coach/index.tsx", coachScreenSource);

    expect(jsxElementCount(source, "InfoCard")).toBe(2);
    expect(jsxElementCount(source, "CoachCheckInReviewSection")).toBe(1);
    expect(jsxElementCount(source, "Tabs")).toBe(0);
    expect(jsxElementCount(source, "Stack")).toBe(0);
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

  it("does not flag a comment that names a prohibited API or category", () => {
    const synthetic = [
      "// Never use console.error here, and never call setQueryData or rpc.",
      "/* workout_summary and sleep_summary are out of scope, as is created_at. */",
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
      ["polling-or-realtime", "export const options = { refetchInterval: 5 };"],
      [
        "write-path",
        "export const f = (c: { rpc: () => void }) => { c.rpc(); };",
      ],
      [
        "optimistic-cache-write",
        "export const f = (c: { setQueryData: () => void }) => { c.setQueryData(); };",
      ],
      [
        "identity-lookup-inside-the-feature",
        "export const f = (a: { getUser: () => void }) => { a.getUser(); };",
      ],
      ["utc-date-conversion", "export const f = (d: Date) => d.toISOString();"],
      ["other-sharing-category", 'export const category = "workout_summary";'],
      ["wildcard-or-unused-column", 'export const columns = "*";'],
      [
        "wildcard-or-unused-column",
        'export const columns = "id, daily_check_ins(*)";',
      ],
      ["wildcard-or-unused-column", 'export const columns = "id, created_at";'],
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

  it("counts JSX elements it is asked about", () => {
    const synthetic = [
      "export const C = () => (",
      "  <View>",
      "    <InfoCard />",
      "    <InfoCard />",
      "  </View>",
      ");",
    ].join("\n");

    expect(jsxElementCount(parse("synthetic.tsx", synthetic), "InfoCard")).toBe(
      2,
    );
  });
});
