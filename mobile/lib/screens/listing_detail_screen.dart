import 'package:flutter/material.dart';

import '../api/client.dart';
import 'booking_detail_screen.dart';

class ListingDetailScreen extends StatefulWidget {
  const ListingDetailScreen({super.key, required this.listingId});

  final String listingId;

  @override
  State<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends State<ListingDetailScreen> {
  Listing? _listing;
  // MVP: rent starting tomorrow for 1–7 days. Calendar picker is a fast-follow.
  int _days = 1;

  @override
  void initState() {
    super.initState();
    ApiClient.instance
        .listing(widget.listingId)
        .then((l) => setState(() => _listing = l));
  }

  String _isoFromNow(int days) =>
      DateTime.now().add(Duration(days: days)).toIso8601String().substring(0, 10);

  Future<void> _request() async {
    try {
      final booking = await ApiClient.instance
          .requestBooking(widget.listingId, _isoFromNow(1), _isoFromNow(_days));
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
            builder: (_) => BookingDetailScreen(bookingId: booking.id)),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('Could not request: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = _listing;
    if (l == null) {
      return Scaffold(
          appBar: AppBar(),
          body: const Center(child: CircularProgressIndicator()));
    }
    final rental = l.pricePerDayCents * _days;
    final fee = (rental * 0.15).round().clamp(100, 1 << 31);

    return Scaffold(
      appBar: AppBar(title: Text(l.title)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Condition: ${l.condition}'
              '${l.ratingCount > 0 ? ' · ★ ${l.ratingAvg}' : ''}'),
          if (l.description.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(l.description),
          ],
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${dollars(l.pricePerDayCents)}/day',
                      style: Theme.of(context).textTheme.titleLarge),
                  if (l.depositCents > 0)
                    Text('Refundable deposit hold: ${dollars(l.depositCents)}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              IconButton(
                onPressed: () => setState(() => _days = (_days - 1).clamp(1, 7)),
                icon: const Icon(Icons.remove_circle_outline),
              ),
              Text('$_days day${_days > 1 ? 's' : ''} (starting tomorrow)'),
              IconButton(
                onPressed: () => setState(() => _days = (_days + 1).clamp(1, 7)),
                icon: const Icon(Icons.add_circle_outline),
              ),
            ],
          ),
          Text(
            'Total: ${dollars(rental + fee)}  '
            '(${dollars(rental)} rental + ${dollars(fee)} service fee)',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 12),
          FilledButton(onPressed: _request, child: const Text('Request to rent')),
          const SizedBox(height: 8),
          const Text(
            "You're only charged if the owner accepts. The exact pickup "
            'address is shared after confirmation.',
            style: TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ],
      ),
    );
  }
}
