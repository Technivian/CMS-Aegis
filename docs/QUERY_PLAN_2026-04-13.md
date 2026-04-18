51 objects imported automatically (use -v 2 for details).

# Query Plan Report (2026-04-13)

Generated via `QuerySet.explain()` for core contract repository/list paths.

## org ordered by updated_at desc

```
4 0 60 SEARCH contracts_contract USING INDEX ctr_org_upd_ix (organization_id=?)
```

## org + status ordered by updated_at desc

```
4 0 60 SEARCH contracts_contract USING INDEX ctr_org_stat_upd_ix (organization_id=? AND status=?)
```

## org + end_date ordered by end_date

```
4 0 60 SEARCH contracts_contract USING INDEX ctr_org_end_ix (organization_id=? AND end_date>?)
```

## org + renewal_date ordered by renewal_date

```
4 0 60 SEARCH contracts_contract USING INDEX ctr_org_renew_ix (organization_id=? AND renewal_date>?)
```

