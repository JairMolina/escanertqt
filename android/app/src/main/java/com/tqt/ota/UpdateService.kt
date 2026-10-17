package com.tqt.ota

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager

/** User-started transfers only. A killed process never silently restarts a flash. */
class UpdateService : Service() {
    private var wake: PowerManager.WakeLock? = null
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val operation = intent?.getStringExtra("operation") ?: run { stopSelf(); return START_NOT_STICKY }
        val notifications = getSystemService(NotificationManager::class.java)
        notifications.createNotificationChannel(NotificationChannel("ota", "Actualización de tarjetas", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val notification = Notification.Builder(this, "ota").setSmallIcon(R.drawable.ic_tqt).setContentTitle("TQT · Actualización Bluetooth")
            .setContentText("Mantén la R2 encendida y cerca. Abre TQT para ver el progreso confirmado.").setContentIntent(open).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(12, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE) else startForeground(12, notification)
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TQT:OTA").apply { acquire(21 * 60 * 1000L) }
        (application as TqtApplication).updates.runTransfer(operation) { stopSelf(startId) }
        return START_NOT_STICKY
    }
    override fun onDestroy() { wake?.let { if (it.isHeld) it.release() }; wake = null; super.onDestroy() }
}
