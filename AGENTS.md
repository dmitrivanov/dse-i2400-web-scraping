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

