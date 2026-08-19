const PROMO_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

export function generatePromoCode(length = 10): string {
  const bytes = new Uint8Array(length)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => PROMO_ALPHABET[b % PROMO_ALPHABET.length]).join("")
}
