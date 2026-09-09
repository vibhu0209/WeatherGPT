# Low-connectivity design

Android downloads one gzip-compressible weather bundle and saves it atomically in Room. Forecast screens read Room as their source of truth. Background refresh defaults to unmetered connectivity, battery-not-low constraints, and exponential backoff; a labelled manual download remains available.

If refresh fails, saved weather stays visible with its retrieval age and stale notice. Offline chat answers only from that saved bundle. An empty cache never produces weather values. New official warnings require connectivity or a separately configured cellular service.

The backend cache is process-local. Production deployment needs shared persistence and distributed rate limiting. Payload-size and network measurements remain in the field evaluation checklist.
