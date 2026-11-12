set timezone to 'UTC';
set extra_float_digits to 1;
select format(
  'select %L, count(*), coalesce(md5(string_agg(h, '''' order by h)), ''-'') '
  'from (select md5(t::text) as h from %I.%I t) rows',
  n.nspname || '.' || c.relname, n.nspname, c.relname
)
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r'
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg\_%'
order by n.nspname, c.relname
\gexec
select format(
  'select %L, ''sequence'', last_value::text || '':'' || is_called::text from %I.%I',
  n.nspname || '.' || c.relname, n.nspname, c.relname
)
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'S'
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg\_%'
order by n.nspname, c.relname
\gexec
