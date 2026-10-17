package com.tqt.ota

import android.app.Application
import androidx.work.*
import com.tqt.ota.data.PrivateStore
import com.tqt.ota.data.TqtApi
import java.util.concurrent.TimeUnit

class TqtApplication : Application() {
    lateinit var store: PrivateStore
    lateinit var api: TqtApi
    lateinit var updates: UpdateManager
    override fun onCreate() {
        super.onCreate()
        store = PrivateStore(this); api = TqtApi(store); updates = UpdateManager(this, store, api)
    }
    fun scheduleSync() {
        val work = OneTimeWorkRequestBuilder<ResultSyncWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS).build()
        // Preserve a new pass even when another worker is finishing an older snapshot.
        WorkManager.getInstance(this).enqueueUniqueWork("tqt-results", ExistingWorkPolicy.APPEND_OR_REPLACE, work)
    }
}
class ResultSyncWorker(context: android.content.Context, parameters: WorkerParameters) : CoroutineWorker(context, parameters) {
    override suspend fun doWork(): Result {
        val app = applicationContext as TqtApplication
        if (app.store.cookie.isEmpty()) return Result.success() // Account login will schedule again.
        return if (app.updates.synchronize()) Result.success() else Result.retry()
    }
}
