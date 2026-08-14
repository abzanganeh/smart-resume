/**
 * Component-level rendering tests for recharts nodes used by /admin/reports.
 *
 * We render charts with fixed width/height (without ResponsiveContainer) and
 * assert that recharts wrappers are emitted into the markup.
 *
 * Run with:
 *   npx tsx tests/components/AdminReportsCharts.test.tsx
 */

import { renderToStaticMarkup } from "react-dom/server"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Funnel,
  FunnelChart,
  LabelList,
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

const activity = [
  { date: "2026-05-01", dau: 120, wau: 540, mau: 1200 },
  { date: "2026-05-02", dau: 140, wau: 560, mau: 1230 },
]

const funnel = [
  { name: "Registered", value: 1000 },
  { name: "Email verified", value: 820 },
  { name: "First build", value: 560 },
  { name: "First export", value: 340 },
  { name: "Subscribed", value: 180 },
]

const revenue = [
  { plan: "monthly_pro", revenue_usd: 2400 },
  { plan: "weekly", revenue_usd: 480 },
  { plan: "monthly_plus", revenue_usd: 900 },
]

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  // eslint-disable-next-line no-console
  console.log(`  PASS: ${message}`)
}

function runTests() {
  // eslint-disable-next-line no-console
  console.log("\nAdminReports recharts render tests\n")

  // Line chart render
  {
    const html = renderToStaticMarkup(
      <LineChart width={600} height={300} data={activity}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Line dataKey="dau" stroke="#F59E0B" dot={false} />
        <Line dataKey="wau" stroke="#3B82F6" dot={false} />
        <Line dataKey="mau" stroke="#10B981" dot={false} />
      </LineChart>,
    )
    assert(html.includes("recharts-wrapper"), "line chart renders recharts wrapper")
  }

  // Bar chart render
  {
    const html = renderToStaticMarkup(
      <BarChart width={600} height={300} data={revenue}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="plan" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="revenue_usd" fill="#F59E0B" />
      </BarChart>,
    )
    assert(html.includes("recharts-wrapper"), "bar chart renders recharts wrapper")
  }

  // Funnel chart render
  {
    const html = renderToStaticMarkup(
      <FunnelChart width={700} height={300}>
        <Tooltip />
        <Funnel data={funnel} dataKey="value">
          <LabelList dataKey="name" position="right" />
        </Funnel>
      </FunnelChart>,
    )
    assert(html.includes("recharts-wrapper"), "funnel chart renders recharts wrapper")
  }

  // eslint-disable-next-line no-console
  console.log("\nAll recharts render tests passed.\n")
}

if (
  typeof process !== "undefined" &&
  process.argv[1]?.endsWith("AdminReportsCharts.test.tsx")
) {
  runTests()
}

