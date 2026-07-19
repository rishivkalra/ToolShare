import 'package:flutter/material.dart';

import '../api/client.dart';
import 'booking_detail_screen.dart';

const _stateLabels = {
  'requested': 'Awaiting owner approval',
  'approved': 'Approved — payment pending',
  'confirmed': 'Confirmed — arrange pickup',
  'picked_up': 'Rental in progress',
  'returned': 'Returned',
  'completed': 'Completed',
  'declined': 'Declined',
  'expired': 'Expired',
  'cancelled_by_borrower': 'Cancelled by borrower',
  'cancelled_by_lender': 'Cancelled by owner',
  'disputed': 'In dispute',
};

class BookingsScreen extends StatefulWidget {
  const BookingsScreen({super.key});

  @override
  State<BookingsScreen> createState() => _BookingsScreenState();
}

class _BookingsScreenState extends State<BookingsScreen> {
  List<Booking> _bookings = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final bookings = await ApiClient.instance.myBookings();
      setState(() => _bookings = bookings);
    } catch (_) {
      // Surface errors through the empty state; pull-to-refresh retries.
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My rentals')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _bookings.isEmpty && !_loading
            ? ListView(
                children: const [
                  Padding(
                    padding: EdgeInsets.all(48),
                    child: Text('No rentals yet.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: Colors.grey)),
                  ),
                ],
              )
            : ListView.builder(
                itemCount: _bookings.length,
                itemBuilder: (context, i) {
                  final b = _bookings[i];
                  return ListTile(
                    leading: const Icon(Icons.handshake_outlined),
                    title: Text(b.listingTitle),
                    subtitle: Text(
                        '${b.startDate} → ${b.endDate} · ${dollars(b.totalCents)}\n'
                        '${_stateLabels[b.state] ?? b.state}'),
                    isThreeLine: true,
                    onTap: () async {
                      await Navigator.push(
                        context,
                        MaterialPageRoute(
                            builder: (_) =>
                                BookingDetailScreen(bookingId: b.id)),
                      );
                      _load();
                    },
                  );
                },
              ),
      ),
    );
  }
}
