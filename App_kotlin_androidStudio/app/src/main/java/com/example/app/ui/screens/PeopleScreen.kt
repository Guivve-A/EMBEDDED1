package com.example.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.app.network.EnrolledPersonDto
import com.example.app.ui.components.GoldButton
import com.example.app.ui.components.PremiumCard
import com.example.app.ui.theme.BlackAbsolute
import com.example.app.ui.theme.DangerRed
import com.example.app.ui.theme.GoldPrimary
import com.example.app.ui.theme.SurfaceCard
import com.example.app.ui.theme.TextPrimary
import com.example.app.ui.theme.TextSecondary
import com.example.app.ui.viewmodel.PeopleViewModel

@Composable
fun PeopleScreen(
    onBack: () -> Unit,
    onEnroll: () -> Unit,
    vm: PeopleViewModel = viewModel(),
) {
    val ui by vm.ui.collectAsStateWithLifecycle()

    // Refresca al entrar Y al volver de "Aprender Rostro" (el ViewModel se
    // conserva en el back stack; sin esto la lista quedaría desactualizada y
    // parecería que solo se guardó 1 persona).
    LaunchedEffect(Unit) { vm.refresh() }

    PremiumScreen(title = "Personas", subtitle = "Rostros autorizados", onBack = onBack) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Acción principal SIEMPRE visible y arriba (antes era un FAB muy abajo).
            GoldButton(
                text = "Aprender Rostro",
                onClick = onEnroll,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Registra a cada miembro de la familia con su nombre y rostro.",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary,
            )
            Spacer(modifier = Modifier.height(20.dp))

            when {
                ui.loading -> Box(
                    Modifier.fillMaxWidth().weight(1f),
                    Alignment.Center,
                ) { CircularProgressIndicator(color = GoldPrimary) }

                ui.errorMessage != null -> PremiumCard(Modifier.fillMaxWidth()) {
                    Text("No se pudo cargar", style = MaterialTheme.typography.titleMedium, color = DangerRed)
                    Text(ui.errorMessage!!, style = MaterialTheme.typography.bodyMedium, color = TextSecondary)
                }

                ui.people.isEmpty() -> PremiumCard(Modifier.fillMaxWidth()) {
                    Text("Aún no hay rostros aprendidos", style = MaterialTheme.typography.titleMedium, color = TextPrimary)
                    Text(
                        "Pulsa \"Aprender Rostro\" para registrar a la primera persona.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary,
                    )
                }

                else -> LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxWidth().weight(1f),
                ) {
                    items(ui.people, key = { it.name }) { person ->
                        PersonCard(person = person, onDelete = { vm.requestDelete(person.name) })
                    }
                }
            }
        }
    }

    ui.pendingDelete?.let { name ->
        AlertDialog(
            onDismissRequest = { vm.cancelDelete() },
            containerColor = SurfaceCard,
            title = { Text("Eliminar persona", color = TextPrimary) },
            text = { Text("¿Quitar a \"$name\" de los rostros autorizados?", color = TextSecondary) },
            confirmButton = {
                TextButton(onClick = { vm.confirmDelete() }, enabled = !ui.deleting) {
                    Text(if (ui.deleting) "Eliminando…" else "Eliminar", color = DangerRed)
                }
            },
            dismissButton = {
                TextButton(onClick = { vm.cancelDelete() }) { Text("Cancelar", color = GoldPrimary) }
            },
        )
    }
}

@Composable
private fun PersonCard(person: EnrolledPersonDto, onDelete: () -> Unit) {
    PremiumCard(modifier = Modifier.fillMaxWidth()) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
            // Avatar circular dorado con inicial.
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(RoundedCornerShape(50))
                    .background(BlackAbsolute),
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(2.dp)
                        .clip(RoundedCornerShape(50))
                        .background(SurfaceCard),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = person.name.take(1).uppercase(),
                        style = MaterialTheme.typography.headlineMedium,
                        color = GoldPrimary,
                    )
                }
            }
            Text(
                text = person.name,
                style = MaterialTheme.typography.titleMedium,
                color = TextPrimary,
                modifier = Modifier.padding(top = 12.dp),
            )
            Text(
                text = "${person.n_embeddings} muestra(s)",
                style = MaterialTheme.typography.labelSmall,
                color = TextSecondary,
                modifier = Modifier.padding(top = 2.dp),
            )
            Box(
                modifier = Modifier
                    .padding(top = 12.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .clickable { onDelete() }
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Delete, contentDescription = "Eliminar", tint = DangerRed, modifier = Modifier.size(18.dp))
                    Text("Eliminar", color = DangerRed, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 6.dp))
                }
            }
        }
    }
}
