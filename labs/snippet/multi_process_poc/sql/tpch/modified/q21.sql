select
    s_name,
    count(*) as numwait
from
    supplier,
    lineitem l1,
    orders,
    nation
group by
    s_name
order by
    numwait desc,
    s_name
limit 100;