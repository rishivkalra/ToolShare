import { useEffect, useState } from 'react';
import { Alert, Button, Linking, StyleSheet, Text, TextInput, View } from 'react-native';

import { api, setAuthToken, UserProfile } from '../api/client';

/**
 * MVP profile screen.
 *
 * Auth wiring: in production, sign in with Firebase (Sign in with Apple /
 * Google / phone OTP) and call setAuthToken(idToken). Against a local dev
 * backend, type any uid below to act as that user ("dev tokens").
 */
export default function ProfileScreen() {
  const [devUid, setDevUid] = useState('demo');
  const [profile, setProfile] = useState<UserProfile | null>(null);

  const signIn = async () => {
    setAuthToken(`dev:${devUid}`);
    try {
      setProfile(await api.me());
    } catch (e: any) {
      Alert.alert('Sign-in failed', e.message);
    }
  };

  useEffect(() => {
    signIn();
  }, []);

  const startPayouts = async () => {
    try {
      const { onboarding_url } = await api.startConnectOnboarding();
      Linking.openURL(onboarding_url);
    } catch (e: any) {
      Alert.alert('Could not start onboarding', e.message);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.label}>Dev sign-in (uid)</Text>
      <View style={styles.row}>
        <TextInput style={styles.input} value={devUid} onChangeText={setDevUid} autoCapitalize="none" />
        <Button title="Switch" onPress={signIn} />
      </View>

      {profile && (
        <View style={styles.card}>
          <Text style={styles.name}>{profile.display_name || profile.uid}</Text>
          <Text style={styles.meta}>
            {profile.rating_count > 0
              ? `★ ${profile.rating_avg} (${profile.rating_count} reviews)`
              : 'No reviews yet'}
          </Text>
        </View>
      )}

      <View style={styles.section}>
        <Button title="Set up payouts (Stripe)" onPress={startPayouts} />
        <Text style={styles.fineprint}>
          Required once before your first payout. Stripe handles identity and bank details —
          ToolShare never sees them.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16, gap: 8 },
  label: { fontWeight: '600' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: { flex: 1, borderWidth: 1, borderColor: '#ccc', borderRadius: 10, padding: 10 },
  card: { backgroundColor: '#f4f4f5', borderRadius: 12, padding: 14, marginTop: 12 },
  name: { fontSize: 18, fontWeight: '700' },
  meta: { color: '#555', marginTop: 4 },
  section: { marginTop: 24 },
  fineprint: { color: '#777', fontSize: 12, marginTop: 6 },
});
