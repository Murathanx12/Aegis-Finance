export const meta = {
  name: 'aegis-chunk',
  description: 'Roadmap chunks: one builder per chunk in its own worktree, an adversarial reviewer per PR, one fix round. Never merges.',
  whenToUse: 'Three or more independent roadmap chunks, after the owner has asked for a workflow. Launch by scriptPath with args; dryRun: true prints the plan and starts no agent.',
  phases: [
    { title: 'Build', detail: 'one builder per chunk, in the worktree the brain created' },
    { title: 'Review', detail: 'fresh-context reviewer tries to refute the PR' },
    { title: 'Fix', detail: 'only when the reviewer reports blockers' },
    { title: 'Recheck', detail: 'the reviewer re-reads each blocker after the fix' },
  ],
}

// args = {
//   rulesPath:  absolute path of BUILDER_RULES.md,
//   reportDir:  absolute directory for <chunk>_REPORT.md and <chunk>_out\,
//   mainSha:    origin/main at launch (the brain fetched it),
//   wave:       the owner's limits for this wave in plain words (spend, hard stop, what is read-only),
//   maxParallel: builders alive at once (default 3; 5 is the ceiling on this PC),
//   builderModel / reviewerModel: optional model overrides (default builder 'opus', reviewer inherits),
//   dryRun:     true = validate and return the plan, start no agent,
//   chunks: [{ id, row, worktree, branch, brief, state }]
//     id       short name, used for the report file          e.g. "ch13-autopsy"
//     row      the roadmap row id                            e.g. "CH-13"
//     worktree absolute path, created by the brain from origin/main
//     branch   branch checked out there
//     brief    goal, acceptance receipt, files it may touch, what is ruled out
//     state    optional: what already exists in the worktree (an interrupted builder's work)
// }

const a = args || {}
const chunks = Array.isArray(a.chunks) ? a.chunks : []
const problems = []
for (const k of ['rulesPath', 'reportDir', 'mainSha', 'wave']) {
  if (!a[k] || typeof a[k] !== 'string') problems.push(`args.${k} is missing`)
}
if (!chunks.length) problems.push('args.chunks is empty')
chunks.forEach((c, i) => {
  for (const k of ['id', 'row', 'worktree', 'branch', 'brief']) {
    if (!c || !c[k] || typeof c[k] !== 'string') problems.push(`chunks[${i}].${k} is missing`)
  }
})
const ids = chunks.map(c => c && c.id)
if (new Set(ids).size !== ids.length) problems.push('two chunks share an id')
const trees = chunks.map(c => c && c.worktree)
if (new Set(trees).size !== trees.length) problems.push('two chunks share a worktree')
if (problems.length) throw new Error('REFUSED: ' + problems.join('; '))

const maxParallel = Math.max(1, Math.min(5, Number(a.maxParallel) || 3))
if (Number(a.maxParallel) > 5) log('maxParallel capped at 5 (RAM on this PC)')
const builderModel = a.builderModel || 'opus'
const reviewerModel = a.reviewerModel || undefined

if (a.dryRun) {
  return {
    dryRun: true,
    maxParallel,
    builderModel,
    reviewerModel: reviewerModel || 'inherits the session model',
    batches: Array.from({ length: Math.ceil(chunks.length / maxParallel) }, (_, b) =>
      chunks.slice(b * maxParallel, (b + 1) * maxParallel).map(c => `${c.row} ${c.id} -> ${c.branch}`)),
    agentsAtMost: chunks.length * 4,
  }
}

const BUILD = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['PR_OPEN', 'PARTIAL', 'BLOCKED'] },
    pr_number: { type: 'integer' },
    head_sha: { type: 'string' },
    tests_run: { type: 'array', items: { type: 'string' } },
    tests_passed: { type: 'boolean' },
    report_path: { type: 'string' },
    claims: { type: 'array', items: { type: 'string' }, description: 'each a checkable statement with the command that shows it' },
    not_done: { type: 'array', items: { type: 'string' } },
    not_verified: { type: 'array', items: { type: 'string' } },
    by_hand: { type: 'array', items: { type: 'string' }, description: 'runtime-side steps for the brain or the owner' },
  },
  required: ['status', 'tests_passed', 'report_path', 'claims', 'not_done', 'not_verified', 'by_hand'],
}

const FINDING = {
  type: 'object',
  properties: {
    file: { type: 'string' },
    line: { type: 'integer' },
    claim: { type: 'string' },
    evidence: { type: 'string', description: 'the command you ran and the output line that shows it' },
    failure_scenario: { type: 'string' },
  },
  required: ['file', 'claim', 'evidence', 'failure_scenario'],
}

const REVIEW = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['MERGE', 'FIX', 'REJECT'] },
    blockers: { type: 'array', items: FINDING },
    majors: { type: 'array', items: FINDING },
    builder_claims_refuted: { type: 'array', items: { type: 'string' } },
    checked: { type: 'array', items: { type: 'string' } },
    not_checked: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'blockers', 'majors', 'builder_claims_refuted', 'checked', 'not_checked'],
}

const RECHECK = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['MERGE', 'FIX', 'REJECT'] },
    still_open: { type: 'array', items: FINDING },
    closed: { type: 'array', items: { type: 'string' } },
    new_problems: { type: 'array', items: FINDING },
  },
  required: ['verdict', 'still_open', 'closed', 'new_problems'],
}

const common = c => `Rules file (read it whole, first): ${a.rulesPath}
Owner limits for this wave: ${a.wave}
origin/main at launch: ${a.mainSha}
Roadmap row: ${c.row} in docs/ROADMAP.md (read the row and what it cites, in your worktree).
Worktree: ${c.worktree}   Branch: ${c.branch}   (exists already; do not create another)
Report: ${a.reportDir}\\${c.id}_REPORT.md   Outputs: ${a.reportDir}\\${c.id}_out\\`

const buildPrompt = c => `You are the builder for one roadmap chunk of Aegis Finance.

${common(c)}

Brief:
${c.brief}
${c.state ? `
State of the worktree (an earlier builder was interrupted; this work is unreviewed):
${c.state}
Read it before writing. Keep what is sound, fix or drop what is not, and say which in the report.
` : ''}
Build the smallest version that produces the acceptance receipt named in the row, test it with
targeted test files, commit early, push, open a PR against main, and poll CI with single
\`gh pr checks <n>\` calls. Do not merge. Return the structured result: every entry of "claims"
is a statement a reviewer can check, with the command that shows it.`

const reviewPrompt = (c, build) => `You are the adversarial reviewer of one pull request in Aegis Finance. You did not write it.
Your job is to find what is wrong with it. A review that finds nothing must say what it checked.

${common(c)}
PR: ${build.pr_number ? '#' + build.pr_number : 'none opened; review the branch diff against origin/main'}

Read the rules file, then the roadmap row, then the diff (\`gh pr diff\` or \`git -C ${c.worktree} diff origin/main...HEAD\`).
You may run the targeted tests in the worktree. You edit nothing, push nothing, merge nothing.

Check, in this order:
1. Does it meet the row's acceptance as written, or a weaker thing with the same name?
2. Can each refusal go red (non-zero exit)? Can each health line go red? Is any "0" always 0?
3. Look-ahead, target leakage, omitted costs, survivor-only panels, a candidate set whose age and
   size are not printed, a positive number without by-year / leave-one-year-out / random control.
4. Does anything write into the runtime checkout or its data, call a broker, a provider or the
   network, or put personal-financial or licensed data in the repo?
5. New module without a caller or a reachability row; new refusal class not enrolled in CASES;
   a test that reads a growing local file, the clock, or a literal date.
6. The builder's own claims, one by one. These are claims, not facts:
${(build.claims || []).map((s, i) => `   ${i + 1}. ${s}`).join('\n') || '   (none given)'}

A blocker is something that makes the result wrong, unsafe, or not the thing the row asks for.
Every finding carries the command you ran and the output that shows it. If you are not sure a
problem is real, put it under majors and say what would settle it.`

const fixPrompt = (c, build, review) => `You are the builder for one roadmap chunk of Aegis Finance, continuing a PR that a reviewer sent back.

${common(c)}
PR: ${build.pr_number ? '#' + build.pr_number : 'none yet'}

The reviewer's blockers. Reproduce each one first. Fix it if it is real; if it is not, say why
with the command that shows it. Do not widen the change beyond these:
${JSON.stringify(review.blockers, null, 1)}

Majors, to fix when the fix is small and to list as not done otherwise:
${JSON.stringify(review.majors, null, 1)}

Run the targeted tests, commit, push to the same branch, append to the report. Do not merge.`

const recheckPrompt = (c, build, review) => `You are the adversarial reviewer of PR ${build.pr_number ? '#' + build.pr_number : '(branch ' + c.branch + ')'} in Aegis Finance, second pass.

${common(c)}

The builder says these blockers are fixed. Re-run the command that showed each one, on the new
head. Mark it closed only if the output changed for the right reason. Then read the fix diff for
new problems it introduced. You edit nothing.
${JSON.stringify(review.blockers, null, 1)}`

async function runChunk(c) {
  const build = await agent(buildPrompt(c), {
    label: `build:${c.id}`, phase: 'Build', schema: BUILD, model: builderModel,
  })
  if (!build) return { id: c.id, row: c.row, recommendation: 'BUILDER_DIED', build: null }
  if (build.status === 'BLOCKED') {
    return { id: c.id, row: c.row, recommendation: 'BLOCKED_READ_REPORT', build }
  }
  const review = await agent(reviewPrompt(c, build), {
    label: `review:${c.id}`, phase: 'Review', schema: REVIEW, model: reviewerModel,
  })
  if (!review) return { id: c.id, row: c.row, recommendation: 'NOT_REVIEWED', build }
  if (review.verdict !== 'FIX' || !review.blockers.length) {
    return {
      id: c.id, row: c.row, build, review,
      recommendation: review.verdict === 'MERGE' ? 'BRAIN_VERIFIES_THEN_MERGES' : 'REVIEWER_' + review.verdict,
    }
  }
  const fix = await agent(fixPrompt(c, build, review), {
    label: `fix:${c.id}`, phase: 'Fix', schema: BUILD, model: builderModel,
  })
  if (!fix) return { id: c.id, row: c.row, build, review, recommendation: 'FIX_BUILDER_DIED' }
  const recheck = await agent(recheckPrompt(c, build, review), {
    label: `recheck:${c.id}`, phase: 'Recheck', schema: RECHECK, model: reviewerModel,
  })
  const clean = recheck && recheck.verdict === 'MERGE' && !recheck.still_open.length && !recheck.new_problems.length
  if (!clean) log(`${c.id}: not clean after one fix round; no second round is run, the brain decides`)
  return {
    id: c.id, row: c.row, build, review, fix, recheck,
    recommendation: clean ? 'BRAIN_VERIFIES_THEN_MERGES' : 'STILL_OPEN_AFTER_ONE_FIX_ROUND',
  }
}

const results = []
for (let i = 0; i < chunks.length; i += maxParallel) {
  const batch = chunks.slice(i, i + maxParallel)
  log(`batch ${i / maxParallel + 1}: ${batch.map(c => c.id).join(', ')}`)
  const out = await parallel(batch.map(c => () => runChunk(c)))
  out.forEach((r, j) => results.push(r || { id: batch[j].id, row: batch[j].row, recommendation: 'CHAIN_FAILED' }))
}
return { mainSha: a.mainSha, results }
