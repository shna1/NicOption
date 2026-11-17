# NicOption

NicOption is a Persian-language options research and position-management application built for the Tehran Stock Exchange and Iran Mercantile Exchange ecosystem.

It combines an options-screening engine with covered-call analysis, long-call-versus-underlying comparisons, trade records, underlying inventory, scenario analysis and performance reporting. The portfolio edition uses Django for the application layer and supports PostgreSQL for multi-session persistence.

> **Research software:** NicOption was developed as a personal analytical project. It has not been used to operate a brokerage account, execute orders or guarantee trading outcomes. The outputs are screening results, not investment advice.

![NicOption market research interface](bambo_bot/web_static/assets/nicoption-og.png)

## What is included

- Tehran and commodity-exchange option-chain adapters,
- covered-call candidate selection and scoring,
- long-call versus underlying comparison,
- contract normalization and option mathematics,
- open and closed trade management,
- covered-underlying inventory and allocation tracking,
- expiry and early-close workflows,
- scenario and profit-recognition views,
- account-level performance summaries,
- CSV import/export helpers,
- Django authentication and per-user data ownership,
- SQLite for local development and PostgreSQL configuration for deployment,
- security controls for CSRF, sessions and login throttling,
- responsive Persian right-to-left web interface, and
- automated Python, Django and JavaScript tests.

## Architecture

```text
bambo_bot/                Core market adapters, calculations and strategy engine
nicoption_dashboard/      Django models, API views, services and migrations
nicoption_site/           Django settings, routes and WSGI/ASGI entry points
bambo_bot/web_static/     Persian RTL front end
tests/                    Core engine tests
nicoption_dashboard/tests Django and API tests
```

The strategy engine remains separated from persistence and presentation. This makes financial calculations testable without running the web application, while Django owns authentication, database records and HTTP boundaries.

## Local setup

Python 3.11 or newer is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 manage.py migrate
python3 manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000`.

The default development configuration uses SQLite. No database file, account, trade record or user export is included in this repository.

## PostgreSQL

Set a PostgreSQL connection URL before migration:

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/nicoption'
python3 manage.py migrate
python3 manage.py runserver
```

`compose.production.yml` and `Dockerfile.django` document the containerized application topology. They contain placeholders only; production secrets must be supplied outside Git.

## Tests

```bash
python3 manage.py check
python3 manage.py makemigrations --check --dry-run
python3 manage.py test nicoption_dashboard
python3 -m unittest discover -s tests -v
node tests/test_financial_csv.js
```

Some market-adapter tests use mocked responses. Running the application against live sources depends on upstream availability and the relevant providers' access and redistribution terms.

## Financial methodology

Covered-call analysis combines the underlying purchase cost, option premium, strike, contract size and remaining time. Long-call comparisons discount the strike using a configurable annual rate. Position records preserve the opening assumptions so that later P&L is not silently recalculated from a different cost basis.

The codebase distinguishes quoted opportunity metrics from realized trade records. An attractive annualized figure is not treated as a forecast or executable return.

## Data sources

The application contains adapters for public market information exposed by TSETMC and the Iran Mercantile Exchange, plus optional economic-data integrations. Users are responsible for confirming current access rules, attribution requirements and redistribution rights before enabling or publishing live data.

This portfolio edition intentionally excludes:

- local databases and user accounts,
- open and closed trade exports,
- generated static bundles and caches,
- prepared datasets and private reports,
- production server scripts and operational identifiers,
- API keys, tokens and email credentials, and
- any archived executable or installer.

## Known limitations

- Screening is not order execution and does not verify fill probability.
- Bid–ask spread, market impact, queue priority and position limits may invalidate a displayed opportunity.
- Annualizing short-dated option returns can produce unstable headline values.
- Corporate actions and contract-specification changes require fresh validation.
- Upstream market schemas and availability can change without notice.
- Forecast and scenario modules are research tools, not probability-calibrated guarantees.
- PostgreSQL concurrency support does not replace operational monitoring, backups or a security review.

## Publication status

This repository is a sanitized portfolio edition of the project. It is suitable for code review and demonstration after the maintainer confirms that live-source usage and branding are acceptable for public distribution. It should not be described as a production brokerage or automated-trading system.

## Author

**Shabar Naderi** — Financial Data Analyst and Python developer focused on quantitative research and Iranian financial markets.

NicOption was independently designed and developed by Shabar Naderi. My work on the project includes:

- financial logic and covered-call analysis,
- backend architecture and Django implementation,
- PostgreSQL data modeling,
- position-management and reporting workflows, and
- the Persian right-to-left research interface.

- [GitHub](https://github.com/shna1)
- [LinkedIn](https://www.linkedin.com/in/shabar-naderi-1b7623b2/)

## Copyright

Copyright © 2026 Shabar Naderi. All rights reserved. This repository is published for portfolio review and evaluation; no permission is granted to copy, modify, distribute or use the code without written authorization. See [COPYRIGHT.md](COPYRIGHT.md).
