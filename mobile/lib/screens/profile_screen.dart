import 'package:flutter/material.dart';

import '../api/client.dart';

/// MVP profile screen.
///
/// Auth wiring: in production, sign in with Firebase (Sign in with Apple /
/// Google / phone OTP) and call ApiClient.instance.setToken(idToken).
/// Against a local dev backend, type any uid below to act as that user.
class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  final _uid = TextEditingController(text: 'demo');
  UserProfile? _profile;

  @override
  void initState() {
    super.initState();
    _signIn();
  }

  Future<void> _signIn() async {
    ApiClient.instance.setToken('dev:${_uid.text.trim()}');
    try {
      final profile = await ApiClient.instance.me();
      setState(() => _profile = profile);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Sign-in failed: $e')));
    }
  }

  Future<void> _addPaymentMethod() async {
    try {
      final bundle = await ApiClient.instance.setupIntent();
      if (!mounted) return;
      // Production: hand this bundle to flutter_stripe's PaymentSheet —
      //   Stripe.instance.initPaymentSheet(SetupPaymentSheetParameters(
      //     setupIntentClientSecret: bundle.setupIntentClientSecret,
      //     customerId: bundle.customerId,
      //     customerEphemeralKeySecret: bundle.ephemeralKeySecret,
      //     applePay/googlePay: ...))
      //   then Stripe.instance.presentPaymentSheet().
      // Dev backend returns fake secrets, so just confirm the wiring.
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
              'Payment setup ready (customer ${bundle.customerId}). '
              'PaymentSheet opens here in production.')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Payment setup failed: $e')));
    }
  }

  Future<void> _startPayouts() async {
    try {
      final url = await ApiClient.instance.connectOnboardingUrl();
      if (!mounted) return;
      // MVP: show the Stripe onboarding URL; production opens it in a browser
      // via url_launcher.
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Stripe onboarding'),
          content: SelectableText(url),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Close')),
          ],
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not start onboarding: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _profile;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _uid,
                  decoration: const InputDecoration(
                    labelText: 'Dev sign-in (uid)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(onPressed: _signIn, child: const Text('Switch')),
            ],
          ),
          const SizedBox(height: 16),
          if (p != null)
            Card(
              child: ListTile(
                leading: const CircleAvatar(child: Icon(Icons.person)),
                title: Text(p.displayName.isNotEmpty ? p.displayName : p.uid),
                subtitle: Text(p.ratingCount > 0
                    ? '★ ${p.ratingAvg} (${p.ratingCount} reviews)'
                    : 'No reviews yet'),
              ),
            ),
          const SizedBox(height: 24),
          OutlinedButton.icon(
            onPressed: _addPaymentMethod,
            icon: const Icon(Icons.credit_card),
            label: const Text('Add payment method'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _startPayouts,
            icon: const Icon(Icons.account_balance),
            label: const Text('Set up payouts (Stripe)'),
          ),
          const SizedBox(height: 8),
          const Text(
            'Required once before your first payout. Stripe handles identity '
            'and bank details — ToolShare never sees them.',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ),
    );
  }
}
