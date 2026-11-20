# Dataset acquisition and identity

The experiment requires the exact file `sales_large.csv` with this identity:

- SHA-256: `bff70d62204d7d53eda5f3d4a9696b9d39be7f43c0f104e09a4f3b30a122c867`
- Expected input rows: `1,000,000`
- Expected output occurrences after null removal and `amount > 0`: `966,002`
- Required in the release directory as: `dataset/sales_large.csv`

The bytes are intentionally not included in this transfer package and are not proposed for GitHub publication. Obtain the authorized copy from the project owner or the approved institutional storage location, then run:

```bash
sha256sum dataset/sales_large.csv
wc -l dataset/sales_large.csv
```

The row-count command includes the header, so the expected line count is dataset-contract dependent; the runner/oracle is authoritative for the 1,000,000 input-row contract. A hash mismatch is a hard stop. Do not substitute `scripts/generate_sales_data.py`, a downloaded sample, or a regenerated file and call it the primary replication dataset. No synthetic generator is included in this release.

