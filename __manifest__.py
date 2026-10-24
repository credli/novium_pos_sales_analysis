{
    "name": "POS Sales Analysis",
    "version": "18.0.1.0.0",
    "summary": "Pivot-first POS sales analysis: hour of day, weekday, day part, "
    "hero / core / dog items and more.",
    "description": """
POS Sales Analysis
==================

Adds **Point of Sale > Reporting > Sales Analysis**, an order-line level report
built for pivoting (expand rows/columns freely, then use the pivot's
*Download xlsx* button to take it to Excel).

Dimensions
----------
* Hour of day (local time of the company), weekday, day part, month, date
* Point of sale, session, cashier, customer, payment method
* Product, product category, POS category
* **Item class** - *Hero* (products making the first 80% of revenue of their
  POS in that month), *Core* (next 15%) and *Dog* (last 5%)

Measures
--------
Quantity, revenue (excl. / incl. tax), discount, cost, margin and order count.
""",
    "author": "Novium SARL",
    "maintainer": "Novium SARL",
    "website": "https://www.novium.io",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "security/pos_sales_analysis_security.xml",
        "views/pos_sales_analysis_views.xml",
    ],
    "installable": True,
    "application": False,
}
