SET SQL_SAFE_UPDATES =0;
UPDATE kirazee_test.universal_Categories
SET category_image = REPLACE(category_image, 'https://dev-kirazee.zdotapps.in/kirazee/', '')
WHERE category_image LIKE 'https://dev-kirazee.zdotapps.in/kirazee/%';