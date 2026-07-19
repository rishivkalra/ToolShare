import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { RouteProp, useRoute } from '@react-navigation/native';

import { api, Booking, dollars, Message } from '../api/client';
import type { RootStackParamList } from '../../App';

export default function BookingDetailScreen() {
  const route = useRoute<RouteProp<RootStackParamList, 'BookingDetail'>>();
  const bookingId = route.params.bookingId;
  const [booking, setBooking] = useState<Booking | null>(null);
  const [me, setMe] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');

  const load = useCallback(() => {
    api.booking(bookingId).then(setBooking).catch(() => {});
    api.messages(bookingId).then(setMessages).catch(() => {});
    api.me().then((u) => setMe(u.uid)).catch(() => {});
  }, [bookingId]);

  useEffect(load, [load]);

  if (!booking) return <Text style={styles.loading}>Loading…</Text>;

  const isLender = me === booking.lender_uid;
  const act = (fn: () => Promise<Booking>) => () =>
    fn().then(setBooking).catch((e) => Alert.alert('Action failed', e.message));

  const actions: { title: string; onPress: () => void }[] = [];
  if (booking.state === 'requested' && isLender) {
    actions.push({ title: 'Approve & charge borrower', onPress: act(() => api.approve(bookingId)) });
    actions.push({ title: 'Decline', onPress: act(() => api.decline(bookingId)) });
  }
  if (booking.state === 'confirmed') {
    const mine = isLender ? booking.lender_marked_pickup : booking.borrower_marked_pickup;
    if (!mine) {
      actions.push({ title: 'Confirm handoff (pickup)', onPress: act(() => api.confirmPickup(bookingId)) });
    }
    actions.push({ title: 'Cancel booking', onPress: act(() => api.cancel(bookingId)) });
  }
  if (booking.state === 'picked_up' && isLender) {
    actions.push({ title: 'Tool returned — all good', onPress: act(() => api.confirmReturn(bookingId)) });
  }
  if (booking.state === 'completed') {
    actions.push({
      title: 'Leave a 5★ review',
      onPress: () =>
        api.leaveReview(bookingId, 5, '').then(load).catch((e) => Alert.alert('Review failed', e.message)),
    });
  }

  const send = () => {
    if (!draft.trim()) return;
    api.sendMessage(bookingId, draft.trim()).then(() => {
      setDraft('');
      api.messages(bookingId).then(setMessages);
    });
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <Text style={styles.title}>{booking.listing_title}</Text>
      <Text style={styles.meta}>
        {booking.start_date} → {booking.end_date} · {dollars(booking.price.total_cents)} ·{' '}
        {booking.state.replace(/_/g, ' ')}
      </Text>
      {booking.exact_address ? (
        <Text style={styles.address}>Pickup: {booking.exact_address}</Text>
      ) : null}

      {actions.map((a) => (
        <View key={a.title} style={styles.action}>
          <Button title={a.title} onPress={a.onPress} />
        </View>
      ))}

      <Text style={styles.chatHeader}>Messages</Text>
      <FlatList
        style={styles.chat}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.sender_uid === me ? styles.mine : styles.theirs]}>
            <Text>{item.text}</Text>
          </View>
        )}
      />
      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          placeholder="Message your neighbor…"
          value={draft}
          onChangeText={setDraft}
          onSubmitEditing={send}
        />
        <Button title="Send" onPress={send} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  loading: { padding: 24, textAlign: 'center' },
  title: { fontSize: 20, fontWeight: '700' },
  meta: { color: '#555', marginTop: 4 },
  address: { marginTop: 6, fontWeight: '600' },
  action: { marginTop: 8 },
  chatHeader: { fontWeight: '600', marginTop: 16 },
  chat: { flex: 1, marginTop: 8 },
  bubble: { padding: 10, borderRadius: 12, marginBottom: 6, maxWidth: '80%' },
  mine: { backgroundColor: '#dcedff', alignSelf: 'flex-end' },
  theirs: { backgroundColor: '#f0f0f0', alignSelf: 'flex-start' },
  composer: { flexDirection: 'row', gap: 8, alignItems: 'center', paddingTop: 8 },
  input: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 10 },
});
