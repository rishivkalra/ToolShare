/**
 * Typed client for the ToolShare FastAPI backend.
 *
 * Auth: in production, pass the Firebase ID token. Against a local dev
 * backend (TOOLSHARE_ENV=dev) you can use "dev:<uid>" tokens instead.
 */

export type ToolCategory =
  | 'power_tools' | 'hand_tools' | 'garden' | 'ladders_access'
  | 'painting_decorating' | 'plumbing' | 'automotive' | 'cleaning'
  | 'measuring' | 'other';

export type BookingState =
  | 'requested' | 'approved' | 'confirmed' | 'picked_up' | 'returned'
  | 'completed' | 'declined' | 'expired' | 'cancelled_by_borrower'
  | 'cancelled_by_lender' | 'disputed';

export interface Listing {
  id: string;
  owner_uid: string;
  title: string;
  category: ToolCategory;
  description: string;
  condition: string;
  photos: string[];
  price_per_day_cents: number;
  deposit_cents: number;
  approx_lat: number;
  approx_lng: number;
  status: 'active' | 'paused' | 'removed';
  rating_avg: number;
  rating_count: number;
}

export interface SearchResult { listing: Listing; distance_km: number; }

export interface PriceBreakdown {
  days: number;
  price_per_day_cents: number;
  rental_cents: number;
  service_fee_cents: number;
  total_cents: number;
  deposit_cents: number;
}

export interface Booking {
  id: string;
  listing_id: string;
  listing_title: string;
  borrower_uid: string;
  lender_uid: string;
  start_date: string;
  end_date: string;
  state: BookingState;
  price: PriceBreakdown;
  borrower_marked_pickup: boolean;
  lender_marked_pickup: boolean;
  exact_address: string;
}

export interface Message { id: string; sender_uid: string; text: string; created_at: string; }

export interface UserProfile {
  uid: string;
  display_name: string;
  photo_url: string;
  rating_avg: number;
  rating_count: number;
}

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8080';

let authToken = '';
export const setAuthToken = (t: string) => { authToken = t; };

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.json().then((j) => j.detail).catch(() => resp.statusText);
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return resp.json();
}

export const api = {
  me: () => req<UserProfile>('GET', '/v1/users/me'),
  updateMe: (b: Partial<UserProfile>) => req<UserProfile>('PATCH', '/v1/users/me', b),
  startConnectOnboarding: () =>
    req<{ onboarding_url: string }>('POST', '/v1/users/me/connect'),

  search: (lat: number, lng: number, radiusKm = 5, q = '', category?: ToolCategory) => {
    const p = new URLSearchParams({ lat: String(lat), lng: String(lng), radius_km: String(radiusKm) });
    if (q) p.set('q', q);
    if (category) p.set('category', category);
    return req<SearchResult[]>('GET', `/v1/listings/search?${p}`);
  },
  listing: (id: string) => req<Listing>('GET', `/v1/listings/${id}`),
  myListings: () => req<Listing[]>('GET', '/v1/listings/mine'),
  createListing: (b: object) => req<Listing>('POST', '/v1/listings', b),

  requestBooking: (listingId: string, start: string, end: string) =>
    req<Booking>('POST', '/v1/bookings', { listing_id: listingId, start_date: start, end_date: end }),
  myBookings: () => req<Booking[]>('GET', '/v1/bookings'),
  booking: (id: string) => req<Booking>('GET', `/v1/bookings/${id}`),
  approve: (id: string) => req<Booking>('POST', `/v1/bookings/${id}/approve`),
  decline: (id: string) => req<Booking>('POST', `/v1/bookings/${id}/decline`),
  cancel: (id: string) => req<Booking>('POST', `/v1/bookings/${id}/cancel`),
  confirmPickup: (id: string) => req<Booking>('POST', `/v1/bookings/${id}/pickup`),
  confirmReturn: (id: string) => req<Booking>('POST', `/v1/bookings/${id}/return`),

  messages: (bookingId: string) => req<Message[]>('GET', `/v1/bookings/${bookingId}/messages`),
  sendMessage: (bookingId: string, text: string) =>
    req<Message>('POST', `/v1/bookings/${bookingId}/messages`, { text }),

  leaveReview: (bookingId: string, stars: number, text: string) =>
    req<object>('POST', `/v1/bookings/${bookingId}/reviews`, { stars, text }),
};

export const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`;
