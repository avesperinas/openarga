update money.money_v1_account set type = 'etf' where type = 'crypto';
update money.money_v1_fund set asset = 'other' where asset = 'crypto';
