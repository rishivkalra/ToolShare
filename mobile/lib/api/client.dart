/// Typed client for the ToolShare FastAPI backend.
///
/// Auth: in production, pass the Firebase ID token via [ApiClient.setToken].
/// Against a local dev backend (TOOLSHARE_ENV=dev) use "dev:&lt;uid&gt;" tokens.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

const String kDefaultBaseUrl =
    String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8080');

String dollars(int cents) => '\$${(cents / 100).toStringAsFixed(2)}';

class Listing {
  final String id;
  final String ownerUid;
  final String title;
  final String category;
  final String description;
  final String condition;
  final int pricePerDayCents;
  final int depositCents;
  final double approxLat;
  final double approxLng;
  final double ratingAvg;
  final int ratingCount;

  Listing.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        ownerUid = j['owner_uid'],
        title = j['title'],
        category = j['category'],
        description = j['description'] ?? '',
        condition = j['condition'] ?? 'good',
        pricePerDayCents = j['price_per_day_cents'],
        depositCents = j['deposit_cents'] ?? 0,
        approxLat = (j['approx_lat'] as num).toDouble(),
        approxLng = (j['approx_lng'] as num).toDouble(),
        ratingAvg = ((j['rating_avg'] ?? 0) as num).toDouble(),
        ratingCount = j['rating_count'] ?? 0;
}

class SearchResult {
  final Listing listing;
  final double distanceKm;

  SearchResult.fromJson(Map<String, dynamic> j)
      : listing = Listing.fromJson(j['listing']),
        distanceKm = (j['distance_km'] as num).toDouble();
}

class Booking {
  final String id;
  final String listingTitle;
  final String borrowerUid;
  final String lenderUid;
  final String startDate;
  final String endDate;
  final String state;
  final int totalCents;
  final bool borrowerMarkedPickup;
  final bool lenderMarkedPickup;
  final String exactAddress;

  Booking.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        listingTitle = j['listing_title'] ?? '',
        borrowerUid = j['borrower_uid'],
        lenderUid = j['lender_uid'],
        startDate = j['start_date'],
        endDate = j['end_date'],
        state = j['state'],
        totalCents = j['price']['total_cents'],
        borrowerMarkedPickup = j['borrower_marked_pickup'] ?? false,
        lenderMarkedPickup = j['lender_marked_pickup'] ?? false,
        exactAddress = j['exact_address'] ?? '';
}

class Message {
  final String id;
  final String senderUid;
  final String text;

  Message.fromJson(Map<String, dynamic> j)
      : id = j['id'],
        senderUid = j['sender_uid'],
        text = j['text'];
}

class PlannedTool {
  final String name;
  final String category;
  final String why;
  final bool optional;

  PlannedTool.fromJson(Map<String, dynamic> j)
      : name = j['name'],
        category = j['category'],
        why = j['why'],
        optional = j['optional'] ?? false;
}

class KitItem {
  final PlannedTool tool;
  final List<Listing> matches;

  KitItem.fromJson(Map<String, dynamic> j)
      : tool = PlannedTool.fromJson(j['tool']),
        matches =
            (j['matches'] as List).map((m) => Listing.fromJson(m)).toList();
}

class ProjectKit {
  final String projectSummary;
  final String safetyNote;
  final String consumablesNote;
  final List<KitItem> kit;
  final int totalEstimatedPerDayCents;
  final List<String> missingTools;

  ProjectKit.fromJson(Map<String, dynamic> j)
      : projectSummary = j['plan']['project_summary'],
        safetyNote = j['plan']['safety_note'] ?? '',
        consumablesNote = j['plan']['consumables_note'] ?? '',
        kit = (j['kit'] as List).map((k) => KitItem.fromJson(k)).toList(),
        totalEstimatedPerDayCents = j['total_estimated_per_day_cents'],
        missingTools = List<String>.from(j['missing_tools']);
}

class UserProfile {
  final String uid;
  final String displayName;
  final double ratingAvg;
  final int ratingCount;

  UserProfile.fromJson(Map<String, dynamic> j)
      : uid = j['uid'],
        displayName = j['display_name'] ?? '',
        ratingAvg = ((j['rating_avg'] ?? 0) as num).toDouble(),
        ratingCount = j['rating_count'] ?? 0;
}

class ApiException implements Exception {
  final int status;
  final String detail;
  ApiException(this.status, this.detail);

  @override
  String toString() => detail;
}

class ApiClient {
  ApiClient({this.baseUrl = kDefaultBaseUrl});

  final String baseUrl;
  String _token = '';

  static final ApiClient instance = ApiClient();

  void setToken(String token) => _token = token;

  Future<dynamic> _req(String method, String path, [Object? body]) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = {
      'Content-Type': 'application/json',
      if (_token.isNotEmpty) 'Authorization': 'Bearer $_token',
    };
    late http.Response resp;
    switch (method) {
      case 'GET':
        resp = await http.get(uri, headers: headers);
      case 'POST':
        resp = await http.post(uri, headers: headers, body: jsonEncode(body));
      case 'PATCH':
        resp = await http.patch(uri, headers: headers, body: jsonEncode(body));
      default:
        throw ArgumentError(method);
    }
    final decoded = resp.body.isEmpty ? null : jsonDecode(resp.body);
    if (resp.statusCode >= 400) {
      final detail = decoded is Map ? '${decoded['detail']}' : resp.body;
      throw ApiException(resp.statusCode, detail);
    }
    return decoded;
  }

  // Users
  Future<UserProfile> me() async => UserProfile.fromJson(await _req('GET', '/v1/users/me'));

  Future<String> connectOnboardingUrl() async =>
      (await _req('POST', '/v1/users/me/connect'))['onboarding_url'];

  // Listings
  Future<List<SearchResult>> search(double lat, double lng,
      {double radiusKm = 8, String q = ''}) async {
    final query = Uri(queryParameters: {
      'lat': '$lat',
      'lng': '$lng',
      'radius_km': '$radiusKm',
      if (q.isNotEmpty) 'q': q,
    }).query;
    final data = await _req('GET', '/v1/listings/search?$query') as List;
    return data.map((j) => SearchResult.fromJson(j)).toList();
  }

  Future<Listing> listing(String id) async =>
      Listing.fromJson(await _req('GET', '/v1/listings/$id'));

  Future<Listing> createListing(Map<String, dynamic> body) async =>
      Listing.fromJson(await _req('POST', '/v1/listings', body));

  // Bookings
  Future<Booking> requestBooking(String listingId, String start, String end) async =>
      Booking.fromJson(await _req('POST', '/v1/bookings', {
        'listing_id': listingId,
        'start_date': start,
        'end_date': end,
      }));

  Future<List<Booking>> myBookings() async =>
      ((await _req('GET', '/v1/bookings')) as List)
          .map((j) => Booking.fromJson(j))
          .toList();

  Future<Booking> booking(String id) async =>
      Booking.fromJson(await _req('GET', '/v1/bookings/$id'));

  Future<Booking> bookingAction(String id, String action) async =>
      Booking.fromJson(await _req('POST', '/v1/bookings/$id/$action'));

  // Chat
  Future<List<Message>> messages(String bookingId) async =>
      ((await _req('GET', '/v1/bookings/$bookingId/messages')) as List)
          .map((j) => Message.fromJson(j))
          .toList();

  Future<void> sendMessage(String bookingId, String text) =>
      _req('POST', '/v1/bookings/$bookingId/messages', {'text': text});

  // Reviews
  Future<void> leaveReview(String bookingId, int stars, String text) =>
      _req('POST', '/v1/bookings/$bookingId/reviews', {'stars': stars, 'text': text});

  // AI project kits
  Future<ProjectKit> planProject(String description, double lat, double lng) async =>
      ProjectKit.fromJson(await _req('POST', '/v1/projects/plan', {
        'description': description,
        'lat': lat,
        'lng': lng,
      }));
}
