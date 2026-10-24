from odoo import fields, models, tools

# Share of cumulative revenue (per POS and month) covered by each class.
HERO_THRESHOLD = 0.80
CORE_THRESHOLD = 0.95  # everything beyond this is a "dog"


class PosSalesAnalysis(models.Model):
    _name = "pos.sales.analysis"
    _description = "POS Sales Analysis"
    _auto = False
    _order = "date desc"
    _rec_name = "order_id"

    date = fields.Datetime(string="Order Date", readonly=True)
    day = fields.Date(string="Day (local)", readonly=True)
    month = fields.Date(string="Month (local)", readonly=True)
    hour = fields.Selection(
        [(f"{h:02d}", f"{h:02d}:00") for h in range(24)],
        string="Hour", readonly=True)
    weekday = fields.Selection(
        [("1", "Monday"), ("2", "Tuesday"), ("3", "Wednesday"), ("4", "Thursday"),
         ("5", "Friday"), ("6", "Saturday"), ("7", "Sunday")],
        string="Weekday", readonly=True)
    day_part = fields.Selection(
        [("1_morning", "Morning (before 11:00)"),
         ("2_lunch", "Lunch (11:00-14:59)"),
         ("3_afternoon", "Afternoon (15:00-18:59)"),
         ("4_evening", "Evening (19:00+)")],
        string="Day Part", readonly=True)
    item_class = fields.Selection(
        [("hero", "Hero"), ("core", "Core"), ("dog", "Dog")],
        string="Item Class", readonly=True,
        help="Hero: products making the first 80% of the revenue of their POS "
             "in that month. Core: next 15%. Dog: last 5%.")

    order_id = fields.Many2one("pos.order", string="Order", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    user_id = fields.Many2one("res.users", string="Cashier", readonly=True)
    config_id = fields.Many2one("pos.config", string="Point of Sale", readonly=True)
    session_id = fields.Many2one("pos.session", string="Session", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    payment_method_id = fields.Many2one(
        "pos.payment.method", string="Payment Method", readonly=True)
    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    product_categ_id = fields.Many2one(
        "product.category", string="Product Category", readonly=True)
    pos_categ_id = fields.Many2one(
        "pos.category", string="POS Category", readonly=True)
    state = fields.Selection(
        [("paid", "Paid"), ("done", "Posted"), ("invoiced", "Invoiced")],
        string="Status", readonly=True)

    qty = fields.Float(string="Quantity", readonly=True)
    price_subtotal = fields.Float(string="Revenue (excl. tax)", readonly=True)
    price_total = fields.Float(string="Revenue (incl. tax)", readonly=True)
    discount_amount = fields.Float(string="Discount", readonly=True)
    cost = fields.Float(string="Cost", readonly=True)
    margin = fields.Float(string="Margin", readonly=True)
    order_count = fields.Float(
        string="Orders", readonly=True,
        help="Each order is split across its lines so that the sum is the "
             "exact number of orders at any grouping level.")

    def _query(self):
        return f"""
            WITH base AS (
                SELECT
                    l.id AS id,
                    s.id AS order_id,
                    s.date_order AS date,
                    (s.date_order AT TIME ZONE 'UTC'
                        AT TIME ZONE COALESCE(NULLIF(cp.tz, ''), 'UTC')) AS local_dt,
                    s.partner_id,
                    s.user_id,
                    s.company_id,
                    s.session_id,
                    ps.config_id,
                    CASE WHEN s.account_move IS NOT NULL THEN 'invoiced' ELSE s.state END AS state,
                    l.product_id,
                    pt.categ_id AS product_categ_id,
                    l.qty AS qty,
                    l.price_subtotal / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS price_subtotal,
                    l.price_subtotal_incl / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS price_total,
                    (l.qty * l.price_unit) * (l.discount / 100.0)
                        / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS discount_amount,
                    COALESCE(l.total_cost, 0) / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS cost,
                    (l.price_subtotal - COALESCE(l.total_cost, 0))
                        / COALESCE(NULLIF(s.currency_rate, 0), 1.0) AS margin,
                    1.0 / COUNT(*) OVER (PARTITION BY s.id) AS order_count,
                    (SELECT (array_agg(pp.payment_method_id ORDER BY pp.id))[1]
                       FROM pos_payment pp WHERE pp.pos_order_id = s.id) AS payment_method_id,
                    (SELECT pc.id
                       FROM pos_category_product_template_rel rel
                       JOIN pos_category pc ON pc.id = rel.pos_category_id
                      WHERE rel.product_template_id = pt.id
                      ORDER BY pc.id LIMIT 1) AS pos_categ_id
                FROM pos_order_line l
                JOIN pos_order s ON s.id = l.order_id
                JOIN pos_session ps ON ps.id = s.session_id
                JOIN res_company co ON co.id = s.company_id
                LEFT JOIN res_partner cp ON cp.id = co.partner_id
                LEFT JOIN product_product p ON p.id = l.product_id
                LEFT JOIN product_template pt ON pt.id = p.product_tmpl_id
                WHERE s.state IN ('paid', 'done', 'invoiced')
            ),
            product_month AS (
                SELECT
                    config_id,
                    company_id,
                    date_trunc('month', local_dt)::date AS month,
                    product_id,
                    SUM(price_subtotal) AS revenue
                FROM base
                GROUP BY config_id, company_id, date_trunc('month', local_dt), product_id
            ),
            ranked AS (
                SELECT
                    config_id, company_id, month, product_id,
                    SUM(revenue) OVER w_ord - revenue AS prior_revenue,
                    SUM(revenue) OVER w_all AS total_revenue
                FROM product_month
                WINDOW
                    w_all AS (PARTITION BY config_id, company_id, month),
                    w_ord AS (PARTITION BY config_id, company_id, month
                              ORDER BY revenue DESC, product_id)
            ),
            classified AS (
                SELECT
                    config_id, company_id, month, product_id,
                    CASE
                        WHEN total_revenue <= 0 THEN 'core'
                        WHEN prior_revenue / total_revenue < {HERO_THRESHOLD} THEN 'hero'
                        WHEN prior_revenue / total_revenue < {CORE_THRESHOLD} THEN 'core'
                        ELSE 'dog'
                    END AS item_class
                FROM ranked
            )
            SELECT
                b.id,
                b.date,
                b.local_dt::date AS day,
                date_trunc('month', b.local_dt)::date AS month,
                LPAD(EXTRACT(hour FROM b.local_dt)::int::text, 2, '0') AS hour,
                EXTRACT(isodow FROM b.local_dt)::int::text AS weekday,
                CASE
                    WHEN EXTRACT(hour FROM b.local_dt) < 11 THEN '1_morning'
                    WHEN EXTRACT(hour FROM b.local_dt) < 15 THEN '2_lunch'
                    WHEN EXTRACT(hour FROM b.local_dt) < 19 THEN '3_afternoon'
                    ELSE '4_evening'
                END AS day_part,
                c.item_class,
                b.order_id, b.partner_id, b.user_id, b.config_id, b.session_id,
                b.company_id, b.payment_method_id, b.product_id,
                b.product_categ_id, b.pos_categ_id, b.state,
                b.qty, b.price_subtotal, b.price_total, b.discount_amount,
                b.cost, b.margin, b.order_count
            FROM base b
            LEFT JOIN classified c
                   ON c.product_id IS NOT DISTINCT FROM b.product_id
                  AND c.config_id IS NOT DISTINCT FROM b.config_id
                  AND c.company_id = b.company_id
                  AND c.month = date_trunc('month', b.local_dt)::date
        """

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"CREATE OR REPLACE VIEW {self._table} AS ({self._query()})")
