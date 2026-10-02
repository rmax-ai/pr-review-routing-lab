# Example outputs

`example_mock.md` and `example_mock.csv` are generated from the offline mock
protocol over `cases/public`. They are mechanics demonstrations, not model,
calibration, autonomy, independence, or cost-savings claims.

The report metric table keeps measured and simulated score IDs separate.
Because this example has no measured score rows, measured score values are
explicitly `None`; simulated values are fixture observations. The CSV contains
both record rows and `row_type=metric` rows, including numerator and
denominator values where the metric supplies them. Mock usage remains
partitioned by source, and an unavailable component is retained in the
completeness decision. Token and cost metrics publish `None` with an explicit
reason for all-unavailable, partial, incomplete, or unpriceable usage instead
of a fabricated total.
