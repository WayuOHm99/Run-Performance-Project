/**
 * Lets a test import a source file as text.
 *
 * `source-safety.test.ts` scans this feature's own code for constructs decisions
 * 2, 7, and 10 forbid — a log call, a storage write, a UTC date conversion,
 * `.upsert()`, an optimistic cache write. Reading the files through the bundler's
 * `?raw` query keeps that scan dependency-free: the alternative was Node's `fs`,
 * which would have required adding `@types/node`, and this task owns no
 * dependency manifest.
 */
declare module "*?raw" {
  const content: string;
  export default content;
}
