select
    o_orderpriority,
    count(*) as order_count
from
    orders
group by
    o_orderpriority
order by
    o_orderpriority;
