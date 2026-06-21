package com.example.app.ui.screens

import android.Manifest
import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.example.app.ui.components.GhostButton
import com.example.app.ui.components.GoldButton
import com.example.app.ui.theme.BlackElevated
import com.example.app.ui.theme.BorderSubtle
import com.example.app.ui.theme.DangerRed
import com.example.app.ui.theme.GoldPrimary
import com.example.app.ui.theme.SuccessGreen
import com.example.app.ui.theme.SurfaceCard
import com.example.app.ui.theme.TextPrimary
import com.example.app.ui.theme.TextSecondary
import com.example.app.ui.viewmodel.EnrollViewModel
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState
import java.io.File

@OptIn(ExperimentalPermissionsApi::class)
@Composable
fun EnrollScreen(
    onBack: () -> Unit,
    vm: EnrollViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val context = LocalContext.current

    // Galería: permite elegir varias fotos a la vez (hasta TARGET_SAMPLES).
    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(EnrollViewModel.TARGET_SAMPLES),
    ) { uris -> uris.forEach { vm.addPhoto(it) } }

    // Cámara: TakePicture devuelve éxito y escribe en la Uri que le pasamos.
    var cameraTarget by remember { mutableStateOf<Uri?>(null) }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture(),
    ) { success -> if (success) cameraTarget?.let { vm.addPhoto(it) } }

    // Lanza la cámara creando la Uri destino (solo cuando hay permiso CAMERA).
    val openCamera: () -> Unit = {
        val uri = createImageUri(context)
        cameraTarget = uri
        cameraLauncher.launch(uri)
    }

    // Permiso CAMERA en runtime. Si el usuario concede, abrimos la cámara;
    // si deniega, mostramos un mensaje sin crashear.
    val cameraPermission = rememberPermissionState(Manifest.permission.CAMERA) { granted ->
        if (granted) {
            openCamera()
        } else {
            vm.setError("Permiso de cámara denegado. Habilítalo en Ajustes para tomar fotos.")
        }
    }

    if (ui.success) {
        EnrollSuccess(
            person = ui.successPerson ?: "",
            samples = ui.successSamples,
            onDone = { vm.reset(); onBack() },
        )
        return
    }

    PremiumScreen(title = "Aprender Rostro", subtitle = "Registrar persona autorizada", onBack = onBack) {
        Column(verticalArrangement = Arrangement.spacedBy(20.dp), modifier = Modifier.fillMaxWidth()) {

            // Contador de muestras + guía + miniaturas (toca una para quitarla).
            Text(
                text = "Tomas: ${ui.photos.size} de ${EnrollViewModel.TARGET_SAMPLES}",
                style = MaterialTheme.typography.titleMedium,
                color = GoldPrimary,
            )
            Text(
                text = "Toma ${EnrollViewModel.TARGET_SAMPLES} fotos variadas (ángulo, expresión " +
                    "y luz) para que el sistema aprenda mejor el rostro. Toca una miniatura para quitarla.",
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary,
            )
            if (ui.photos.isEmpty()) {
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Box(
                        modifier = Modifier
                            .size(120.dp)
                            .clip(RoundedCornerShape(50))
                            .background(SurfaceCard),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            Icons.Outlined.Person,
                            contentDescription = null,
                            tint = GoldPrimary,
                            modifier = Modifier.size(56.dp),
                        )
                    }
                }
            } else {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    ui.photos.forEachIndexed { index, uri ->
                        AsyncImage(
                            model = uri,
                            contentDescription = "Toma ${index + 1}",
                            contentScale = ContentScale.Crop,
                            modifier = Modifier
                                .size(58.dp)
                                .clip(RoundedCornerShape(14.dp))
                                .background(SurfaceCard)
                                .clickable { vm.removePhoto(index) },
                        )
                    }
                }
            }

            OutlinedTextField(
                value = ui.name,
                onValueChange = vm::setName,
                label = { Text("Nombre") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = GoldPrimary,
                    unfocusedBorderColor = BorderSubtle,
                    focusedLabelColor = GoldPrimary,
                    unfocusedLabelColor = TextSecondary,
                    cursorColor = GoldPrimary,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary,
                ),
            )

            GhostButton(
                text = "Tomar foto",
                onClick = {
                    if (ui.photos.size >= EnrollViewModel.TARGET_SAMPLES) {
                        vm.setError("Ya tienes ${EnrollViewModel.TARGET_SAMPLES} tomas. Quita alguna para añadir otra.")
                    } else if (cameraPermission.status.isGranted) {
                        // Si ya hay permiso, abrir cámara; si no, solicitarlo en runtime.
                        openCamera()
                    } else {
                        cameraPermission.launchPermissionRequest()
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            )
            GhostButton(
                text = "Elegir de galería",
                onClick = {
                    galleryLauncher.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                    )
                },
                modifier = Modifier.fillMaxWidth(),
            )

            if (ui.errorMessage != null) {
                Text(ui.errorMessage!!, color = DangerRed, style = MaterialTheme.typography.bodyMedium)
            }

            GoldButton(
                text = if (ui.submitting) "Registrando…" else "Registrar (${ui.photos.size} muestras)",
                onClick = { vm.submit() },
                modifier = Modifier.fillMaxWidth(),
                enabled = ui.canSubmit,
            )
        }
    }
}

@Composable
private fun EnrollSuccess(person: String, samples: Int, onDone: () -> Unit) {
    PremiumScreen(title = "Registrado", subtitle = "Rostro aprendido") {
        Column(verticalArrangement = Arrangement.spacedBy(20.dp), modifier = Modifier.fillMaxWidth()) {
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Box(
                    modifier = Modifier
                        .size(120.dp)
                        .clip(RoundedCornerShape(50))
                        .background(BlackElevated),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("OK", style = MaterialTheme.typography.headlineMedium, color = SuccessGreen)
                }
            }
            Text(
                text = "\"$person\" fue registrado con $samples muestra(s).",
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
            )
            GoldButton(text = "Listo", onClick = onDone, modifier = Modifier.fillMaxWidth())
        }
    }
}

/** Crea una Uri content:// (FileProvider) para que la cámara escriba la foto. */
private fun createImageUri(context: Context): Uri {
    val dir = File(context.cacheDir, "camera").apply { mkdirs() }
    val file = File(dir, "capture_${System.currentTimeMillis()}.jpg")
    return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
}
