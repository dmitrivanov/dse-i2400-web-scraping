# Project engineering rules

### Simplicity

- Prefer the simplest correct implementation.
- Use standard Python features whenever possible.
- Do not introduce abstractions unless they solve a demonstrated problem.
- Avoid enterprise architecture, dependency injection frameworks, repositories, factories, service containers, and unnecessary classes.
- Avoid premature optimization.

### Modularity

- Each Python module should have one clearly defined responsibility.
- Use descriptive file names.
- Related small functions may share one file.
- Avoid large multipurpose modules.
- Do not create empty placeholder files for future features.

### Readability

- Write readable Python with descriptive variable and function names.
- Use type hints for public functions where practical.
- Add short docstrings explaining the purpose of nontrivial functions.
- Avoid redundant comments explaining obvious Python syntax.
- Prefer explicit control flow over clever one-line solutions.

### Database

- Use MySQL 8 and `mysql-connector-python`.
- Do not use SQLAlchemy or another ORM.
- Write explicit SQL statements.
- Keep the schema in `sql/schema.sql`.
- Use foreign keys and appropriate constraints.
- Use parameterized SQL for user-supplied values.
- Do not hardcode database credentials.
- Do not perform destructive database operations without explicit permission.
- Database operations must be easy to inspect in MySQL Workbench.
- Commit changes on successful write operations and roll back failed transactions.

### Development process

- Work on one milestone at a time.
- Do not implement functionality outside the requested milestone.
- Do not refactor unrelated code.
- Prefer small, reviewable changes.
- After each task, explain which files were created or changed and why.
- Provide exact commands for testing.
- Report errors and limitations rather than hiding them.
- Never fabricate search results, AI responses, or successful test outcomes.
- Never claim that a test passed unless it actually ran.

### Security

- Store secrets in `.env`.
- Include `.env` in `.gitignore`.
- Provide `.env.example` without actual secrets.
- Never print passwords or API keys in logs or error messages.
- Do not commit credentials or local environment files.

### Learning and transparency

The project owner must understand every component.

When introducing a new library, design pattern, table, or module, explain:

1. What it does.
2. Why it is needed.
3. How it interacts with the other components.
4. How to verify that it works.

## Git and milestone completion policy

- Work on the `main` branch.
- At the beginning of each milestone, inspect the current Git branch and working-tree status.
- Preserve existing user changes and never discard or overwrite uncommitted work.
- Implement only the requested milestone.
- Run relevant automated tests before committing.
- Commit completed milestones automatically to local `main` when acceptance criteria are satisfied.
- Use descriptive commit messages, for example: `Milestone 02: Direct Google search and ETL`.
- Stage only files relevant to the milestone, not indiscriminately every file in the project.
- Never commit `.env`, API keys, credentials, temporary files, or generated artifacts containing sensitive information.
- Do not create commits when tests fail or critical milestone requirements remain unverified.
- Do not automatically push to GitHub. Local commits and remote pushes are separate operations.
- Never force push or reset Git history.
- Report the commit hash and test results after each milestone.
- If the milestone is incomplete because of an external service failure, report the blocker and leave changes uncommitted unless explicitly instructed otherwise.

## Assigned research topic

- Group B: `childhood cancer early diagnosis methods` is the default example query in documentation and demonstrations.
- Support arbitrary valid user queries; do not hardcode the assigned topic in retrieval, ETL, or database modules.
- Collect data for other assigned groups only when explicitly requested.
- Preserve query-to-result foreign-key relationships and never fabricate research data.
