SELECT
  au.*
FROM
  dashboard_customuser dc
  JOIN auth_user au ON au.id = dc.user_id;

DELETE FROM auth_user
WHERE
  id = 6;
