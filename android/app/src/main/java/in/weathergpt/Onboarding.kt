package `in`.weathergpt

import android.content.pm.PackageManager
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.NotificationsNone
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat

private val onboardingProfiles = listOf(
    "general" to R.string.general, "farming" to R.string.farming, "fishing" to R.string.fishing,
    "outdoor" to R.string.outdoor, "tourism" to R.string.tourism, "transport" to R.string.transport,
    "construction" to R.string.construction, "emergency" to R.string.emergency, "vendor" to R.string.vendor,
    "aviation" to R.string.aviation, "research" to R.string.research,
)

@Composable
fun OnboardingScreen(vm: WeatherViewModel, onFinished: (Place?, String) -> Unit) {
    var step by rememberSaveable { mutableStateOf(0) }
    var language by rememberSaveable { mutableStateOf(vm.value("language", "en")) }
    var profile by rememberSaveable { mutableStateOf(vm.value("profile", "general")) }
    var theme by rememberSaveable { mutableStateOf(vm.value("theme", "system")) }
    var large by rememberSaveable { mutableStateOf(vm.value("large") == "true") }
    var purpose by rememberSaveable { mutableStateOf("home") }
    var locating by remember { mutableStateOf(false) }
    var showSearch by rememberSaveable { mutableStateOf(false) }
    val searchBusy by vm.searchBusy.collectAsState()
    val context = LocalContext.current
    val totalSteps = 5
    val locationUnavailable = s(R.string.location_unavailable)

    fun finish(place: Place?) {
        vm.save("language", language)
        vm.save("profile", profile)
        vm.save("theme", theme)
        vm.save("large", large.toString())
        vm.save("onboarded", "true")
        if (vm.value("official_notifications") == "true" || vm.value("risk_notifications") == "true") {
            vm.ensureDeviceRegistration()
            vm.syncAlertSubscription(true)
        }
        onFinished(place, purpose)
    }

    fun useDeviceLocation() {
        locating = true
        DeviceLocation.request(context) { location ->
            if (location == null) {
                locating = false
                Toast.makeText(context, locationUnavailable, Toast.LENGTH_LONG).show()
                showSearch = true
            } else {
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
                        showSearch = true
                    },
                )
            }
        }
    }

    val locationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) useDeviceLocation() else {
            Toast.makeText(context, locationUnavailable, Toast.LENGTH_LONG).show()
            showSearch = true
        }
    }
    val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        vm.save("official_notifications", granted.toString())
        vm.save("risk_notifications", granted.toString())
        if (granted) {
            vm.ensureDeviceRegistration()
            vm.syncAlertSubscription(true)
        }
    }

    if (showSearch) {
        PlaceDialog(
            vm = vm,
            onDismiss = { showSearch = false },
            onChoose = { place, chosenPurpose ->
                purpose = chosenPurpose
                finish(place)
            },
            autoLocate = false,
        )
    }

    Scaffold { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(s(R.string.personalization), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(
                String.format(s(R.string.step_of), step + 1, totalSteps),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
            )
            LinearProgressIndicator(progress = { (step + 1f) / totalSteps }, modifier = Modifier.fillMaxWidth())
            Text(s(R.string.onboard_intro), style = MaterialTheme.typography.bodyLarge)
            Column(
                Modifier.weight(1f).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                when (step) {
                    0 -> {
                        Text(s(R.string.language), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(s(R.string.language_help), style = MaterialTheme.typography.bodyMedium)
                        listOf(
                            "en" to "English", "hi" to "हिन्दी", "bn" to "বাংলা", "te" to "తెలుగు", "mr" to "मराठी",
                            "ta" to "தமிழ்", "gu" to "ગુજરાતી", "kn" to "ಕನ್ನಡ", "ml" to "മലയാളം", "pa" to "ਪੰਜਾਬੀ", "or" to "ଓଡ଼ିଆ",
                        ).forEach { (code, name) ->
                            Choice(name, language == code) {
                                language = code
                                vm.save("language", code)
                            }
                        }
                    }
                    1 -> {
                        Text(s(R.string.use_for), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(s(R.string.occupation_help), style = MaterialTheme.typography.bodyMedium)
                        onboardingProfiles.forEach { (key, label) ->
                            Choice(s(label), profile == key) {
                                profile = key
                                vm.save("profile", key)
                            }
                        }
                    }
                    2 -> {
                        Text(s(R.string.theme), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(s(R.string.theme_help), style = MaterialTheme.typography.bodyMedium)
                        listOf(
                            "system" to R.string.system_theme,
                            "light" to R.string.light_theme,
                            "dark" to R.string.dark_theme,
                        ).forEach { (key, label) ->
                            Choice(s(label), theme == key) {
                                theme = key
                                vm.save("theme", key)
                            }
                        }
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(
                                value = large,
                                onValueChange = {
                                    large = it
                                    vm.save("large", it.toString())
                                },
                            ),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(s(R.string.large_text), Modifier.weight(1f))
                            Switch(checked = large, onCheckedChange = null)
                        }
                    }
                    3 -> {
                        Text(s(R.string.permissions_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(s(R.string.permissions_help), style = MaterialTheme.typography.bodyMedium)
                        val locGranted = DeviceLocation.hasPermission(context)
                        val notifGranted = if (android.os.Build.VERSION.SDK_INT >= 33) {
                            ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
                        } else true
                        OutlinedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(s(R.string.grant_location), fontWeight = FontWeight.Bold)
                                Text(if (locGranted) s(R.string.permissions_granted) else s(R.string.permissions_needed))
                                if (!locGranted) {
                                    BigButton(s(R.string.grant_location), Icons.Default.MyLocation, onClick = {
                                        locationPermission.launch(android.Manifest.permission.ACCESS_COARSE_LOCATION)
                                    })
                                }
                            }
                        }
                        OutlinedCard(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(s(R.string.grant_notifications), fontWeight = FontWeight.Bold)
                                Text(s(R.string.official_notification_help), style = MaterialTheme.typography.bodyMedium)
                                Text(if (notifGranted) s(R.string.permissions_granted) else s(R.string.permissions_needed))
                                if (android.os.Build.VERSION.SDK_INT >= 33 && !notifGranted) {
                                    BigButton(s(R.string.grant_notifications), Icons.Default.NotificationsNone, onClick = {
                                        notificationPermission.launch(android.Manifest.permission.POST_NOTIFICATIONS)
                                    })
                                } else if (android.os.Build.VERSION.SDK_INT < 33) {
                                    Choice(s(R.string.official_notifications), vm.value("official_notifications") == "true") {
                                        vm.save("official_notifications", "true")
                                    }
                                    Choice(s(R.string.risk_notifications), vm.value("risk_notifications") == "true") {
                                        vm.save("risk_notifications", "true")
                                    }
                                }
                            }
                        }
                    }
                    else -> {
                        Text(s(R.string.choose_place), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(s(R.string.location_preferred), style = MaterialTheme.typography.bodyLarge)
                        Text(s(R.string.place_purpose), style = MaterialTheme.typography.titleMedium)
                        listOf(
                            "home" to R.string.purpose_home,
                            "farm" to R.string.purpose_farm,
                            "harbour" to R.string.purpose_harbour,
                            "work" to R.string.purpose_work,
                        ).forEach { (key, label) ->
                            Choice(s(label), purpose == key) { purpose = key }
                        }
                        if (locating || searchBusy) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                CircularProgressIndicator(Modifier.size(28.dp))
                                Text(s(R.string.locating))
                            }
                        } else {
                            BigButton(s(R.string.use_current_location), Icons.Default.MyLocation, onClick = {
                                if (DeviceLocation.hasPermission(context)) useDeviceLocation()
                                else locationPermission.launch(android.Manifest.permission.ACCESS_COARSE_LOCATION)
                            })
                            OutlinedButton(onClick = { showSearch = true }, modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)) {
                                Text(s(R.string.search_place_fallback))
                            }
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (step > 0) {
                    OutlinedButton(onClick = { step -= 1 }, modifier = Modifier.weight(1f).heightIn(min = 56.dp)) {
                        Text(s(R.string.onboard_back))
                    }
                }
                Button(
                    onClick = {
                        when (step) {
                            in 0..3 -> step += 1
                            else -> {
                                if (DeviceLocation.hasPermission(context)) useDeviceLocation()
                                else locationPermission.launch(android.Manifest.permission.ACCESS_COARSE_LOCATION)
                            }
                        }
                    },
                    modifier = Modifier.weight(1f).heightIn(min = 56.dp),
                    enabled = !locating,
                ) {
                    Text(if (step < 4) s(R.string.onboard_next) else s(R.string.onboard_finish))
                }
            }
            if (step == 4) {
                TextButton(onClick = { finish(null) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                    Text(s(R.string.skip_for_now))
                }
            }
        }
    }
}
