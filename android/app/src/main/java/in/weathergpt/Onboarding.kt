package `in`.weathergpt

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val simpleProfiles = listOf(
    "farming" to R.string.farming,
    "fishing" to R.string.fishing,
    "outdoor" to R.string.outdoor,
    "vendor" to R.string.vendor,
    "general" to R.string.general,
)

private val quickPlaces = listOf(
    Place("Delhi", 28.6139, 77.2090),
    Place("Mumbai", 19.0760, 72.8777),
    Place("Bengaluru", 12.9716, 77.5946),
    Place("Chennai", 13.0827, 80.2707),
    Place("Kolkata", 22.5726, 88.3639),
    Place("Hyderabad", 17.3850, 78.4867),
    Place("Pune", 18.5204, 73.8567),
    Place("Lucknow", 26.8467, 80.9462),
)

@Composable
fun OnboardingScreen(vm: WeatherViewModel, onFinished: (Place?, String) -> Unit) {
    var step by rememberSaveable { mutableStateOf(0) }
    var language by rememberSaveable { mutableStateOf(vm.value("language", "en")) }
    var profile by rememberSaveable { mutableStateOf(vm.value("profile", "general")) }
    var locating by remember { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf("") }
    val results by vm.results.collectAsState()
    val searchBusy by vm.searchBusy.collectAsState()
    val context = LocalContext.current
    val locationUnavailable = s(R.string.location_unavailable)

    fun finish(place: Place?) {
        vm.save("language", language)
        vm.save("profile", profile)
        vm.save("theme", "system")
        vm.save("large", "true")
        vm.save("onboarded", "true")
        onFinished(place, when (profile) {
            "farming" -> "farm"
            "fishing" -> "harbour"
            "outdoor", "vendor" -> "work"
            else -> "home"
        })
    }

    fun useDeviceLocation() {
        locating = true
        DeviceLocation.request(context, onResult = { location ->
            if (location == null) {
                locating = false
                Toast.makeText(context, locationUnavailable, Toast.LENGTH_LONG).show()
            } else {
                // Never hang: even if reverse-geocode fails, keep coordinates.
                vm.resolveCurrentLocation(
                    location.latitude,
                    location.longitude,
                    context.getString(R.string.current_location),
                    onResolved = { place ->
                        locating = false
                        finish(place)
                    },
                    onFailed = {
                        locating = false
                        finish(Place(context.getString(R.string.current_location), location.latitude, location.longitude, "Asia/Kolkata"))
                    },
                )
            }
        }, timeoutMs = 7000L)
    }

    val locationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) useDeviceLocation() else Toast.makeText(context, locationUnavailable, Toast.LENGTH_LONG).show()
    }

    Scaffold { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Surface(
                color = MaterialTheme.colorScheme.primaryContainer,
                shape = MaterialTheme.shapes.large,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(s(R.string.simple_setup), style = MaterialTheme.typography.headlineMedium.copy(fontSize = 28.sp), fontWeight = FontWeight.Bold)
                    Text(String.format(s(R.string.step_of), step + 1, 3), style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.primary)
                    LinearProgressIndicator(progress = { (step + 1f) / 3f }, modifier = Modifier.fillMaxWidth().height(8.dp), trackColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.5f))
                }
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                when (step) {
                    0 -> {
                        Text(s(R.string.language), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text(s(R.string.pick_language_help), style = MaterialTheme.typography.bodyLarge)
                        listOf(
                            "hi" to "हिन्दी", "en" to "English", "bn" to "বাংলা", "te" to "తెలుగు", "mr" to "मराठी",
                            "ta" to "தமிழ்", "gu" to "ગુજરાતી", "kn" to "ಕನ್ನಡ", "ml" to "മലയാളം", "pa" to "ਪੰਜਾਬੀ", "or" to "ଓଡ଼ିଆ",
                        ).forEach { (code, name) ->
                            BigChoice(name, language == code) {
                                language = code
                                vm.save("language", code)
                            }
                        }
                    }
                    1 -> {
                        Text(s(R.string.use_for), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text(s(R.string.simple_work_help), style = MaterialTheme.typography.bodyLarge)
                        simpleProfiles.forEach { (key, label) ->
                            BigChoice(s(label), profile == key) {
                                profile = key
                                vm.save("profile", key)
                            }
                        }
                    }
                    else -> {
                        Text(s(R.string.where_do_you_live), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text(s(R.string.search_village_first), style = MaterialTheme.typography.bodyLarge)
                        OutlinedTextField(
                            value = query,
                            onValueChange = { query = it.take(80) },
                            label = { Text(s(R.string.city_village)) },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 72.dp),
                            textStyle = MaterialTheme.typography.titleMedium,
                            singleLine = true,
                        )
                        BigButton(s(R.string.search), Icons.Default.Search, onClick = { vm.search(query) }, enabled = query.trim().length >= 2 && !searchBusy)
                        if (searchBusy || locating) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                CircularProgressIndicator(Modifier.size(28.dp))
                                Text(if (locating) s(R.string.locating) else s(R.string.loading), style = MaterialTheme.typography.titleMedium)
                            }
                        }
                        results.forEach { place ->
                            BigChoice(place.name, false) { finish(place) }
                        }
                        Text(s(R.string.or_pick_city), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                        quickPlaces.forEach { place ->
                            BigChoice(place.name, false) { finish(place) }
                        }
                        HorizontalDivider()
                        BigButton(s(R.string.use_current_location), Icons.Default.MyLocation, onClick = {
                            if (DeviceLocation.hasPermission(context)) useDeviceLocation()
                            else locationPermission.launch(android.Manifest.permission.ACCESS_COARSE_LOCATION)
                        }, enabled = !locating)
                        Text(s(R.string.location_backup_help), style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (step > 0) {
                    OutlinedButton(onClick = { step -= 1 }, modifier = Modifier.weight(1f).heightIn(min = 64.dp)) {
                        Text(s(R.string.onboard_back), style = MaterialTheme.typography.titleMedium)
                    }
                }
                Button(
                    onClick = { if (step < 2) step += 1 },
                    modifier = Modifier.weight(1f).heightIn(min = 64.dp),
                    enabled = step < 2,
                ) {
                    Text(s(R.string.onboard_next), style = MaterialTheme.typography.titleMedium)
                }
            }
        }
    }
}

@Composable
fun BigChoice(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) {
        Button(onClick = onClick, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp), shape = MaterialTheme.shapes.large) {
            Text(label, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(vertical = 8.dp))
        }
    } else {
        OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp), shape = MaterialTheme.shapes.large) {
            Text(label, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(vertical = 8.dp))
        }
    }
}
