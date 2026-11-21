# Reference data seed

From the project root, after installing backend dependencies and reviewing and
applying the initial migration to your chosen database:

```powershell
backend/.venv/Scripts/python.exe -m database.seeds.seed --check-only
backend/.venv/Scripts/python.exe -m database.seeds.seed
```

`--check-only` uses only the Python standard library and never opens a database.
The write command uses `backend/.env`. It inserts missing records inside one
transaction, rejects ID/identity collisions and never deletes or overwrites
existing records. Run one seed process at a time. A concurrent conflicting insert
raises an integrity error and rolls back rather than silently modifying data.

The seed contains 214 rows: 78 cards, 78 Thai card meanings, five categories,
32 questions, three default spreads and 18 ordered positions. IDs are stable: Major Arcana
1–22 map to ranks 0–21 (RWS Strength VIII, Justice XI); Minor Arcana 23–78 follow
Wands, Cups, Swords, Pentacles, each Ace through King. The supplied Thai questions
are preserved verbatim. Recommendations are NULL because the specification does
not prescribe question-specific choices. Alternate spreads can be added later.
The Celtic Cross variant follows `docs/tarot-rules.md` exactly.

Every seeded `image_path` is NULL until all local RWS files are verified and
linked. Each card has a stable expected `image_filename`. Render the labeled
placeholder while the path is NULL. The seed inserts original Thai summaries
for all 78 cards in `card_meanings`, but preserves existing edited meanings on
rerun. Editorial revisions require a separately reviewed update; rerunning the
seed will not overwrite them. See `docs/asset-licenses.md` for asset import.

For artwork imports, review each source page and license as described in
`docs/asset-licenses.md`; the import tool records source, author, edition,
license and local checksum in `database/assets/verified_provenance.json` before
image paths are linked. This seed preserves existing approved image paths,
editorial names and edited meanings. No third-party artwork is downloaded by
the seed command.
