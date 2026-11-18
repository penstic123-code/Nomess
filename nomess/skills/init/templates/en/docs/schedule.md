# Schedule

The single construction entry point: packages, order, file ownership and status live only here. Plan files list no packages, only one line pointing here. `nomess check` reads the columns Package, Depends, Status and Files (C4: packages in progress must not share files).

| Package | What | Files | Depends | Status | Brief / handback |
|---|---|---|---|---|---|

Status values: Todo / Doing / Review / Rework / Merged; the automatic tidy moves Merged rows into the change log of their plan. Files: globs separated by commas; list explicit files where you can.
