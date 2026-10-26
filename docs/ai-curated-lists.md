# AI-curated streamer lists

**Status:** planned, not started. It builds on the personal lists feature. Work starts once two things are done:

- the lists feature is deployed;
- old streams are archived out of Postgres, the planned database optimization.

## The idea

Today a developer finds streamers with the search filters on `/streamers`. This plan adds lists that an AI agent has already built, so developers can skip that step.

- The curated lists become the project's **main product**.
- The filter search becomes the **secondary product**, for developers who want to dig on their own.

## How it would work

- **The agent builds lists by running searches.**
  - It composes search queries for particular kinds of games and audiences.
  - It runs them, then names and describes each resulting list.
- **Lists are rebuilt weekly, on Mondays at 12:00 UTC.** That way every list includes the latest weekend, which is the busiest time for game streams.
- **Lists are tagged.** Each list carries tags that read like search terms, and developers browse and search lists by them. Examples:
  - genres: `shooter`, `adventure`;
  - audience size: `5-20 viewers`;
  - activity: `2-5 streams per week`;
  - language: `en`.
- **The number of lists is decided as it goes.** The first run might be a few dozen lists. Later it could grow to about 100 or 200, depending on how useful the lists prove and what they cost to build.
- **A developer can import a curated list as their own.** The import becomes one of their personal lists. They then edit it to fit their game and their judgement: check streamers, remove some, add others.

## What it builds on

- **A list can already store a search.** Each user list keeps the search it came from in `UserListOfStreamers.search_filters`, with every filter spelled out by `StreamerSearch.explicit_filters()`. So a curated list can be a stored search that gets re-run each week, without a new mechanism.
- **Re-running a list's search is already planned** as step 7 of the lists feature, "Refresh". That step marks streamers as new or missing compared with the list. The weekly rebuild is the same operation on a schedule.
- **Tags can come from the filters.** `StreamerSearch.describe()` already turns a search's filters into label and value pairs. Generating tags the same way keeps them in step with the search behind the list.
- **Import is close to "Save as new list".** That flow (`POST /api/lists/`) saves a search's results. An import would instead copy the curated list's current streamers.
- **Current limits:**
  - a list holds at most 5,000 streamers;
  - a user keeps at most 20 lists.

## Open questions

- **Will Monday's data include Sunday?** `rebuild_search_stats` refreshes streamers in rolling chunks and covers everyone about once a day. So at 12:00 UTC on Monday, some streamers' stats won't include Sunday yet. Two fixes: run a full stats rebuild just before the weekly job, or move the job later.
- **How do per-week tags map to the filters?** The search counts streams over the 4-week window, so "2-5 streams per week" means 8-20 streams in that window. The filter's options include both 8 and 20.
- **How much does the agent do beyond writing queries?** Reviewing individual streamers, for example their recent games and stream titles, would make lists sharper. It would also cost more per list. Measure both on the first few dozen lists.
- **Where do curated lists live?** One option is a model of their own, readable by every signed-in user. The other is lists owned by a system account. They are shared, rebuilt weekly and tagged, which favours a model of their own.
- **Should an imported copy keep in touch with its source?** It could stay a snapshot, as a saved search is today. Or it could pick up the curated list's weekly changes later; step 7's new and missing marks would fit that.
- **Should imports count towards the 20-list limit?**
- **Should each week's version be kept?** History would show which streamers joined or dropped out of a list. It is also data for later retro-analysis.
- **Who gets access?** It could be free for signed-in users or part of a paid tier. A paid tier could, for example, sit alongside the idea of a paid 3-month data window.
