import { useCallback, useState } from 'react';
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';

import { api, Booking, BookingState, dollars } from '../api/client';

const STATE_LABEL: Record<BookingState, string> = {
  requested: 'Awaiting owner approval',
  approved: 'Approved — payment pending',
  confirmed: 'Confirmed — arrange pickup',
  picked_up: 'Rental in progress',
  returned: 'Returned',
  completed: 'Completed',
  declined: 'Declined',
  expired: 'Expired',
  cancelled_by_borrower: 'You cancelled',
  cancelled_by_lender: 'Owner cancelled',
  disputed: 'In dispute',
};

export default function BookingsScreen() {
  const nav = useNavigation<any>();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api.myBookings()
      .then(setBookings)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useFocusEffect(load);

  return (
    <View style={styles.container}>
      <FlatList
        data={bookings}
        keyExtractor={(b) => b.id}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
        ListEmptyComponent={
          !loading ? <Text style={styles.empty}>No rentals yet.</Text> : null
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.card}
            onPress={() => nav.navigate('BookingDetail', { bookingId: item.id })}
          >
            <Text style={styles.title}>{item.listing_title}</Text>
            <Text style={styles.meta}>
              {item.start_date} → {item.end_date} · {dollars(item.price.total_cents)}
            </Text>
            <Text style={styles.state}>{STATE_LABEL[item.state]}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 12 },
  card: { padding: 14, borderRadius: 12, backgroundColor: '#f4f4f5', marginBottom: 8 },
  title: { fontSize: 16, fontWeight: '600' },
  meta: { color: '#555', marginTop: 2 },
  state: { marginTop: 6, fontWeight: '600', color: '#0a7d33' },
  empty: { textAlign: 'center', color: '#777', marginTop: 48 },
});
