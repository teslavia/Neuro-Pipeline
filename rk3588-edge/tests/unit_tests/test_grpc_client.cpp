#include "communication/grpc_client.hpp"
#include "neuro_pipeline.pb.h"
#include <gtest/gtest.h>
#include <thread>
#include <chrono>
#include <vector>

using namespace communication;

class GRPCClientTest : public ::testing::Test {
protected:
    GRPCClient::Config config;

    void SetUp() override {
        config.server_address = "localhost:50051";
        config.initial_backoff_ms = 100;
        config.max_reconnect_attempts = 3;
    }
};

// ---------------------------------------------------------------------------
// Basic lifecycle tests
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, CreateClient) {
    GRPCClient client(config);
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, GetBackoffMs) {
    GRPCClient client(config);
    EXPECT_EQ(client.GetBackoffMs(0), 100);
    EXPECT_EQ(client.GetBackoffMs(1), 200);
    EXPECT_EQ(client.GetBackoffMs(2), 400);
    EXPECT_LE(client.GetBackoffMs(10), 30000);
}

TEST_F(GRPCClientTest, GetBackoffMsClampsToMax) {
    GRPCClient client(config);
    // Even with very high attempt, should not exceed 30s
    EXPECT_EQ(client.GetBackoffMs(20), 30000);
    EXPECT_EQ(client.GetBackoffMs(100), 30000);
}

TEST_F(GRPCClientTest, ConnectWithoutServer) {
    GRPCClient client(config);
    EXPECT_FALSE(client.Connect());
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, ConnectIdempotent) {
    // Calling Connect twice without server should not crash
    GRPCClient client(config);
    EXPECT_FALSE(client.Connect());
    EXPECT_FALSE(client.Connect());
}

TEST_F(GRPCClientTest, DisconnectWhenNotConnected) {
    GRPCClient client(config);
    client.Disconnect();  // Should not crash
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, DisconnectIdempotent) {
    GRPCClient client(config);
    client.Disconnect();
    client.Disconnect();  // Double disconnect should be safe
    EXPECT_FALSE(client.IsConnected());
}

// ---------------------------------------------------------------------------
// Stream tests (no server — expect graceful failure)
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, StreamDetectionWithoutConnection) {
    GRPCClient client(config);
    neuro_pipeline::DetectionResult result;
    result.set_frame_id(1);
    EXPECT_FALSE(client.StreamDetection(result));
}

TEST_F(GRPCClientTest, FlushStreamWithoutOpenStream) {
    GRPCClient client(config);
    EXPECT_FALSE(client.FlushStream());
}

TEST_F(GRPCClientTest, HealthCheckWithoutConnection) {
    GRPCClient client(config);
    EXPECT_FALSE(client.HealthCheck());
}

// ---------------------------------------------------------------------------
// Reconnection tests
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, ReconnectAttemptsExhausted) {
    config.max_reconnect_attempts = 2;
    GRPCClient client(config);

    // Each StreamDetection call triggers a reconnect attempt
    neuro_pipeline::DetectionResult result;
    result.set_frame_id(0);
    EXPECT_FALSE(client.StreamDetection(result));

    result.set_frame_id(1);
    EXPECT_FALSE(client.StreamDetection(result));

    // After max attempts, should fail immediately
    result.set_frame_id(2);
    EXPECT_FALSE(client.StreamDetection(result));
}

// ---------------------------------------------------------------------------
// Config validation
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, ConfigDefaults) {
    GRPCClient::Config defaults;
    EXPECT_FALSE(defaults.server_address.empty());
    EXPECT_GT(defaults.keepalive_interval_ms, 0);
    EXPECT_GT(defaults.keepalive_timeout_ms, 0);
    EXPECT_GT(defaults.max_reconnect_attempts, 0);
    EXPECT_GT(defaults.initial_backoff_ms, 0);
}

TEST_F(GRPCClientTest, ConfigCustomValues) {
    EXPECT_EQ(config.server_address, "localhost:50051");
    EXPECT_EQ(config.initial_backoff_ms, 100);
    EXPECT_EQ(config.max_reconnect_attempts, 3);
}

// ---------------------------------------------------------------------------
// Thread safety smoke test
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, ConcurrentDisconnect) {
    GRPCClient client(config);

    // Multiple threads calling Disconnect concurrently should not crash
    std::vector<std::thread> threads;
    for (int i = 0; i < 4; i++) {
        threads.emplace_back([&client]() {
            client.Disconnect();
        });
    }
    for (auto& t : threads) {
        t.join();
    }
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, ConcurrentStreamAndDisconnect) {
    GRPCClient client(config);

    // One thread tries to stream, another disconnects — should not crash
    std::thread streamer([&client]() {
        neuro_pipeline::DetectionResult result;
        result.set_frame_id(42);
        client.StreamDetection(result);  // Will fail, but should not crash
    });

    std::thread disconnector([&client]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        client.Disconnect();
    });

    streamer.join();
    disconnector.join();
    EXPECT_FALSE(client.IsConnected());
}

// ---------------------------------------------------------------------------
// Event stream tests (no server — expect graceful failure)
// ---------------------------------------------------------------------------

TEST_F(GRPCClientTest, StartEventStreamWithoutConnection) {
    GRPCClient client(config);
    bool called = false;
    EXPECT_FALSE(client.StartEventStream(
        [&called](const neuro_pipeline::ControlCommand&) { called = true; }));
    EXPECT_FALSE(called);
}

TEST_F(GRPCClientTest, SendEdgeEventWithoutStream) {
    GRPCClient client(config);
    neuro_pipeline::EdgeEvent event;
    event.set_type(neuro_pipeline::EdgeEvent::HEALTH_UPDATE);
    EXPECT_FALSE(client.SendEdgeEvent(event));
}

TEST_F(GRPCClientTest, StopEventStreamWhenNotStarted) {
    GRPCClient client(config);
    client.StopEventStream();  // Should not crash
}
