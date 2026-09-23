# Contributor instructions

This repository is the source for the live KB at `kb.konverta.eu`.

- Make code changes here, in a feature branch named `dsh/<short-topic>`; do not commit directly to `main`.
- Keep the DSH prototype under `/home/dsh/Konverta` separate. The connected Git clone is `/home/dsh/workspace/konverta-plastics-kb`.
- Run `pytest` before pushing. UI changes need desktop and mobile checks.
- Add reliable source title and URL for technical claims. Include safety notes where relevant. Unknown polymer compatibility must remain unknown.
- Never commit API keys, OAuth files, Cloudflare credentials, SQLite databases, backups, or generated model/build caches.
- Runtime data is stored in the KB PVC and must not be copied into this repository.
- Push feature branches to `origin`; GitHub Actions runs tests and a container build for every branch. Have a maintainer review and merge changes through a pull request.
- Releases use SemVer tags (`vMAJOR.MINOR.PATCH`) on commits already in `main`. GitHub Actions builds the release image. The server polls private releases every five minutes and deploys the image automatically.
- Do not create or push release tags unless explicitly asked by the maintainer.
