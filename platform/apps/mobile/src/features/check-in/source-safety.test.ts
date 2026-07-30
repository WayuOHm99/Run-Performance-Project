import { describe, expect, it } from "vitest";

import cardSource from "./check-in-card.tsx?raw";
import repositorySource from "./check-in-repository.ts?raw";
import choiceGroupSource from "./choice-group.tsx?raw";
import copySource from "./copy.ts?raw";
import domainSource from "./domain.ts?raw";
import errorsSource from "./errors.ts?raw";
import localDateSource from "./local-date.ts?raw";
import queryOptionsSource from "./query-options.ts?raw";
import submissionSource from "./submission.ts?raw";
import hooksSource from "./use-daily-check-in.ts?raw";

/**
 * Guards for the rules that cannot be observed from behaviour alone.
 *
 * Decision 10 forbids a persisted draft, an outbox, an automatic retry of a
 * health-bearing write, and any health value in a log; decision 2 forbids
 * deriving the local date through a UTC conversion; decision 7 forbids
 * `.upsert()`. Behavioural tests show today's code does none of these — see
 * `logging.test.ts` for the runtime half. Only a source guard stops a later edit
 * from quietly adding one.
 *
 * Assertions are lists of **file names** and counts, never file contents, so a
 * failure says which file broke a rule without reprinting the code or any value.
 *
 * The sources are read through the bundler rather than through Node's `fs`,
 * because `@types/node` is not a dependency of this workspace and this task owns
 * no dependency manifest.
 */

type SourceFile = readonly [name: string, text: string];

const SOURCES: readonly SourceFile[] = [
  ["check-in-card.tsx", cardSource],
  ["check-in-repository.ts", repositorySource],
  ["choice-group.tsx", choiceGroupSource],
  ["copy.ts", copySource],
  ["domain.ts", domainSource],
  ["errors.ts", errorsSource],
  ["local-date.ts", localDateSource],
  ["query-options.ts", queryOptionsSource],
  ["submission.ts", submissionSource],
  ["use-daily-check-in.ts", hooksSource],
];

/**
 * A file's executable code, with comments removed.
 *
 * The documentation in these modules names the very APIs the rules forbid, in
 * order to explain why they are forbidden. Scanning the raw text would flag an
 * accurate comment as a violation, so the scan looks at code only.
 */
function codeOf(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/.*$/gm, " ");
}

function codeIn(name: string): string {
  const found = SOURCES.find(([candidate]) => candidate === name);

  if (found === undefined) {
    throw new Error(`No source registered for ${name}.`);
  }

  return codeOf(found[1]);
}

/** File names whose code contains any of the given fragments. */
function filesContaining(fragments: readonly string[]): readonly string[] {
  return SOURCES.filter(([, text]) => {
    const code = codeOf(text);

    return fragments.some((fragment) => code.includes(fragment));
  }).map(([name]) => name);
}

describe("the check-in feature source", () => {
  it("was actually loaded", () => {
    // Guards against the whole scan passing because it read nothing.
    const empty = SOURCES.filter(([, text]) => text.trim().length === 0).map(
      ([name]) => name,
    );

    expect(empty).toEqual([]);
    expect(SOURCES.length).toBe(10);
  });

  it("logs nothing", () => {
    expect(
      filesContaining([
        "console.",
        "Sentry",
        "trackEvent",
        "logEvent",
        "captureException",
        "recordError",
      ]),
    ).toEqual([]);
  });

  it("persists no draft and no outbox", () => {
    expect(
      filesContaining([
        "AsyncStorage",
        "SecureStore",
        "localStorage",
        "sessionStorage",
        "setItem",
        "getItem",
        "MMKV",
        "persist",
        "outbox",
        "FileSystem",
      ]),
    ).toEqual([]);
  });

  it("schedules no background work and sends no notification", () => {
    expect(
      filesContaining([
        "setInterval",
        "setTimeout",
        "BackgroundFetch",
        "TaskManager",
        "Notifications",
        "registerTask",
      ]),
    ).toEqual([]);
  });

  it("derives the local date without any UTC conversion", () => {
    expect(
      filesContaining([
        "toISOString",
        "toJSON",
        "getUTCFullYear",
        "getUTCMonth",
        "getUTCDate",
        "Date.UTC",
        "toUTCString",
        "toLocaleDateString",
      ]),
    ).toEqual([]);
  });

  it("builds the date from local calendar parts", () => {
    const code = codeIn("local-date.ts");

    expect(
      ["getFullYear", "getMonth", "getDate"].filter(
        (accessor) => !code.includes(accessor),
      ),
    ).toEqual([]);
  });

  it("never reaches for upsert", () => {
    // `.upsert()` would have to name the unique index as a conflict target;
    // decision 7 prohibits it in favour of the update-first algorithm.
    expect(filesContaining(["upsert"])).toEqual([]);
  });

  it("branches on a SQLSTATE rather than on error text", () => {
    const code = codeIn("check-in-repository.ts");

    expect(code.includes('"23505"')).toBe(true);
    // Reading `.message` in control flow is what decision 8 forbids.
    expect(code.includes(".message")).toBe(false);
    expect(code.includes(".details")).toBe(false);
    expect(code.includes(".hint")).toBe(false);
  });

  it("disables mutation retries explicitly", () => {
    expect(codeIn("query-options.ts").includes("retry: 0")).toBe(true);
  });

  it("uses no optimistic cache write for the health values", () => {
    expect(filesContaining(["onMutate", "setQueryData"])).toEqual([]);
  });

  it("reads the athlete id from nothing but the caller-supplied argument", () => {
    // A repository that could look the id up itself could be called without a
    // verified identity. It has no auth access at all, by construction.
    expect(
      filesContaining(["auth.getUser", "auth.getSession", "auth.session"]),
    ).toEqual([]);
  });
});
