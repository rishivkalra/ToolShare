import { useEffect, useState } from 'react';
import { Alert, Button, ScrollView, StyleSheet, Text, View } from 'react-native';
import { RouteProp, useNavigation, useRoute } from '@react-navigation/native';

import { api, dollars, Listing } from '../api/client';
import type { RootStackParamList } from '../../App';

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function ListingDetailScreen() {
  const route = useRoute<RouteProp<RootStackParamList, 'ListingDetail'>>();
  const nav = useNavigation<any>();
  const [listing, setListing] = useState<Listing | null>(null);
  // MVP date picker: rent "tomorrow" for 1–7 days. Replace with a calendar
  // component once the money loop is proven.
  const [days, setDays] = useState(1);

  useEffect(() => {
    api.listing(route.params.listingId).then(setListing).catch(() => {});
  }, [route.params.listingId]);

  if (!listing) return <Text style={styles.loading}>Loading…</Text>;

  const rental = listing.price_per_day_cents * days;
  const fee = Math.max(Math.round(rental * 0.15), 100);

  const request = async () => {
    try {
      const booking = await api.requestBooking(
        listing.id,
        isoDaysFromNow(1),
        isoDaysFromNow(days),
      );
      nav.navigate('BookingDetail', { bookingId: booking.id });
    } catch (e: any) {
      Alert.alert('Could not request', e.message);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>{listing.title}</Text>
      <Text style={styles.meta}>
        Condition: {listing.condition}
        {listing.rating_count > 0 ? ` · ★ ${listing.rating_avg}` : ''}
      </Text>
      {listing.description ? <Text style={styles.desc}>{listing.description}</Text> : null}

      <View style={styles.priceBox}>
        <Text style={styles.price}>{dollars(listing.price_per_day_cents)}/day</Text>
        {listing.deposit_cents > 0 && (
          <Text style={styles.meta}>
            Refundable deposit hold: {dollars(listing.deposit_cents)}
          </Text>
        )}
      </View>

      <View style={styles.daysRow}>
        <Button title="−" onPress={() => setDays(Math.max(1, days - 1))} />
        <Text style={styles.days}>{days} day{days > 1 ? 's' : ''} (starting tomorrow)</Text>
        <Button title="+" onPress={() => setDays(Math.min(7, days + 1))} />
      </View>

      <Text style={styles.total}>
        Total: {dollars(rental + fee)} ({dollars(rental)} rental + {dollars(fee)} service fee)
      </Text>
      <Button title="Request to rent" onPress={request} />
      <Text style={styles.fineprint}>
        You'll only be charged if the owner accepts. Exact pickup address is shared
        after confirmation.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 10 },
  loading: { padding: 24, textAlign: 'center' },
  title: { fontSize: 22, fontWeight: '700' },
  meta: { color: '#555' },
  desc: { fontSize: 15, lineHeight: 21 },
  priceBox: { backgroundColor: '#f4f4f5', borderRadius: 12, padding: 12 },
  price: { fontSize: 18, fontWeight: '600' },
  daysRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  days: { fontSize: 16 },
  total: { fontSize: 16, fontWeight: '600' },
  fineprint: { color: '#777', fontSize: 12, marginTop: 8 },
});
