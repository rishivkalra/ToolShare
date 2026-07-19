import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../api/client.dart';
import 'listing_detail_screen.dart';

Future<Position> currentPosition() async {
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    throw Exception('Location permission is needed to find tools near you.');
  }
  return Geolocator.getCurrentPosition();
}

class BrowseScreen extends StatefulWidget {
  const BrowseScreen({super.key});

  @override
  State<BrowseScreen> createState() => _BrowseScreenState();
}

class _BrowseScreenState extends State<BrowseScreen> {
  final _searchController = TextEditingController();
  List<SearchResult> _results = [];
  bool _loading = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = '';
    });
    try {
      final pos = await currentPosition();
      final results = await ApiClient.instance.search(
        pos.latitude,
        pos.longitude,
        q: _searchController.text.trim(),
      );
      setState(() => _results = results);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tools near you')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              controller: _searchController,
              decoration: const InputDecoration(
                hintText: 'Search: drill, ladder, saw…',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
              ),
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _load(),
            ),
          ),
          if (_error.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Text(_error, style: const TextStyle(color: Colors.red)),
            ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: _results.isEmpty && !_loading
                  ? ListView(
                      children: const [
                        Padding(
                          padding: EdgeInsets.all(48),
                          child: Text(
                            'No tools nearby yet.\nBe the first — list one from the "List" tab.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: Colors.grey),
                          ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      itemCount: _results.length,
                      itemBuilder: (context, i) {
                        final r = _results[i];
                        return ListTile(
                          leading: const Icon(Icons.build_outlined),
                          title: Text(r.listing.title),
                          subtitle: Text(
                            '${dollars(r.listing.pricePerDayCents)}/day · '
                            '${r.distanceKm.toStringAsFixed(1)} km away'
                            '${r.listing.ratingCount > 0 ? ' · ★ ${r.listing.ratingAvg}' : ''}',
                          ),
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) =>
                                  ListingDetailScreen(listingId: r.listing.id),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
