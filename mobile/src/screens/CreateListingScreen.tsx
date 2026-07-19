import { useState } from 'react';
import {
  Alert,
  Button,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from 'react-native';
import * as Location from 'expo-location';

import { api, ToolCategory } from '../api/client';

const CATEGORIES: ToolCategory[] = [
  'power_tools', 'hand_tools', 'garden', 'ladders_access', 'painting_decorating',
  'plumbing', 'automotive', 'cleaning', 'measuring', 'other',
];

export default function CreateListingScreen() {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<ToolCategory>('power_tools');
  const [pricePerDay, setPricePerDay] = useState('8');
  const [deposit, setDeposit] = useState('50');
  const [address, setAddress] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== 'granted') throw new Error('Location is required to place your listing on the map.');
      const loc = await Location.getCurrentPositionAsync({});
      await api.createListing({
        title,
        description,
        category,
        price_per_day_cents: Math.round(parseFloat(pricePerDay || '0') * 100),
        deposit_cents: Math.round(parseFloat(deposit || '0') * 100),
        lat: loc.coords.latitude,
        lng: loc.coords.longitude,
        exact_address: address,
      });
      Alert.alert('Listed!', 'Your tool is now visible to neighbors.');
      setTitle('');
      setDescription('');
    } catch (e: any) {
      Alert.alert('Could not list', e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.label}>What are you lending?</Text>
      <TextInput style={styles.input} placeholder="e.g. DeWalt circular saw" value={title} onChangeText={setTitle} />

      <Text style={styles.label}>Category</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chips}>
        {CATEGORIES.map((c) => (
          <Text
            key={c}
            onPress={() => setCategory(c)}
            style={[styles.chip, c === category && styles.chipActive]}
          >
            {c.replace(/_/g, ' ')}
          </Text>
        ))}
      </ScrollView>

      <Text style={styles.label}>Description (optional)</Text>
      <TextInput
        style={[styles.input, styles.multiline]}
        multiline
        placeholder="Condition notes, blade size, battery included…"
        value={description}
        onChangeText={setDescription}
      />

      <Text style={styles.label}>Price per day ($)</Text>
      <TextInput style={styles.input} keyboardType="decimal-pad" value={pricePerDay} onChangeText={setPricePerDay} />

      <Text style={styles.label}>Refundable deposit ($, 0 for none)</Text>
      <TextInput style={styles.input} keyboardType="decimal-pad" value={deposit} onChangeText={setDeposit} />

      <Text style={styles.label}>Pickup address (only shared after a confirmed booking)</Text>
      <TextInput style={styles.input} placeholder="123 Alder St" value={address} onChangeText={setAddress} />

      <Button title={busy ? 'Listing…' : 'List my tool'} onPress={submit} disabled={busy || title.length < 3} />
      <Text style={styles.fineprint}>
        You keep 100% of your listed price — the borrower pays the service fee.
        Payouts arrive via Stripe after each rental.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 16, gap: 6 },
  label: { fontWeight: '600', marginTop: 10 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 10 },
  multiline: { minHeight: 70, textAlignVertical: 'top' },
  chips: { flexDirection: 'row', marginVertical: 4 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#eee',
    marginRight: 8,
    overflow: 'hidden',
  },
  chipActive: { backgroundColor: '#111', color: '#fff' },
  fineprint: { color: '#777', fontSize: 12, marginTop: 10 },
});
