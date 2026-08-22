/**
 * Apple Pay domain verification file for Stripe Checkout.
 *
 * Stripe Dashboard → Settings → Payment methods → Apple Pay → Add domain
 * provides the file contents. Set APPLE_PAY_DOMAIN_ASSOCIATION in the
 * frontend environment (one line, no quotes) or place the downloaded file at
 * public/.well-known/apple-developer-merchantid-domain-association.
 */
export async function GET() {
  const body = process.env.APPLE_PAY_DOMAIN_ASSOCIATION?.trim();
  if (!body) {
    return new Response("Apple Pay domain association not configured", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
