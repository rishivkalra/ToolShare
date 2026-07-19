import { useCallback, useEffect, useState } from 'react';
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as Location from 'expo-location';
import { useNavigation } from '@react-navigation/native';

import { api, dollars, SearchResult } from '../api/client';

export default function BrowseScreen() {
  const nav = useNavigation<any>();
  const [results, setResults] = useState<SearchResult[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== 'granted') {
        setError('Location permission is needed to find tools near you.');
        return;
      }
      const loc = await Location.getCurrentPositionAsync({});
      const found = await api.search(loc.coords.latitude, loc.coords.longitude, 8, query);
      setResults(found);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, []);

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        placeholder="Search: drill, ladder, saw…"
        value={query}
        onChangeText={setQuery}
        onSubmitEditing={load}
        returnKeyType="search"
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        data={results}
        keyExtractor={(r) => r.listing.id}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.empty}>
              No tools nearby yet. Be the first — list one from the “List a tool” tab.
            </Text>
          ) : null
        }
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.card}
            onPress={() => nav.navigate('ListingDetail', { listingId: item.listing.id })}
          >
            <Text style={styles.title}>{item.listing.title}</Text>
            <Text style={styles.meta}>
              {dollars(item.listing.price_per_day_cents)}/day · {item.distance_km} km away
              {item.listing.rating_count > 0
                ? ` · ★ ${item.listing.rating_avg} (${item.listing.rating_count})`
                : ''}
            </Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 12 },
  search: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 10,
    padding: 10,
    marginBottom: 8,
  },
  card: {
    padding: 14,
    borderRadius: 12,
    backgroundColor: '#f4f4f5',
    marginBottom: 8,
  },
  title: { fontSize: 16, fontWeight: '600' },
  meta: { color: '#555', marginTop: 4 },
  empty: { textAlign: 'center', color: '#777', marginTop: 48, paddingHorizontal: 24 },
  error: { color: '#b00020', marginBottom: 8 },
});
