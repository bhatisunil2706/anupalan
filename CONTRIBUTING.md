# Contributing to Pramaanly

Thanks for helping. Pramaanly is open source under the [Apache License 2.0](LICENSE), and contributions of every size
are welcome.

## Ways to help

- **Report a bug** or **suggest a feature** with the issue templates.
- **Review framework content.** If you're a lawyer, auditor or compliance practitioner, checking our guidance against
  the official texts (DPDP, CERT-In, RBI, SEBI, IRDAI, IFSCA, ISO 27001, SOC 2, PCI DSS and others) is one of the most
  valuable contributions. Open an issue with the framework, the requirement reference and what should change.
- **Fix bugs and add features.** Look for issues labelled `good first issue` or `help wanted`.
- **Add a connector** for a tool you use (see the README's Development section).
- **Improve the documentation** in `backend/app/content/help/`.

For larger changes, please open an issue first so we can agree on the approach before you spend time on it.

## Development setup

See [Development](README.md#development) in the README. In short: Python 3.12+, Node 22+, PostgreSQL 16 and Redis,
or just Docker with `./start.sh`.

## Before you open a pull request

Run the same checks as CI:

```bash
cd backend
ruff check app tests
python -m app.cli check-content
DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/app_test" pytest -q
bandit -q -r app -c pyproject.toml
cd ../frontend && npx tsc --noEmit && npm run build
```

- Add or update tests for what you change. Anything touching data access must keep tenant isolation (row-level
  security) intact; see `tests/test_security.py`.
- Database changes need an Alembic migration (`alembic revision --autogenerate`), and `alembic check` must pass.
- Keep user-facing text plain and specific. Content changes to frameworks must keep every requirement mapped to a
  control (`check-content` enforces this).
- One topic per pull request, with a clear description of what and why.

## Content and licensing rules

- Write it yourself, or use material whose licence is compatible with Apache 2.0, and say where it came from.
- **Don't copy** code, framework libraries, control mappings or questionnaires from commercial or AGPL-licensed
  products, and **don't paste text** from paid standards (ISO, AICPA, PCI SSC). Refer to requirements by number and
  describe them in your own words.
- Check the licence of any new dependency; avoid GPL and AGPL dependencies.

By submitting a contribution, you agree that it is licensed under the Apache License 2.0, as described in section 5
of the licence.

## Security issues

Don't report vulnerabilities in public issues. Use
[private vulnerability reporting](https://github.com/bhatisunil2706/pramaanly/security/advisories/new); see
[SECURITY.md](SECURITY.md).

## Code of conduct

Everyone taking part is expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md).
