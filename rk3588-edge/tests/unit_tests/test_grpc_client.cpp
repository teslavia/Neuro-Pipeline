#include "communication/grpc_client.hpp"
#include "neuro_pipeline.pb.h"
#include <gtest/gtest.h>
#include <thread>
#include <chrono>

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

TEST_F(GRPCClientTest, ConnectWithoutServer) {
    GRPCClient client(config);
    EXPECT_FALSE(client.Connect());
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, DisconnectWhenNotConnected) {
    GRPCClient client(config);
    client.Disconnect();
    EXPECT_FALSE(client.IsConnected());
}

TEST_F(GRPCClientTest, StreamDetectionWithoutConnection) {
    GRPCClient client(config);
    neuro_pipeline::DetectionResult result;
    result.set_frame_id(1);
    EXPECT_FALSE(client.StreamDetection(result));
}

TEST_F(GRPCClientTest, HealthCheckWithoutConnection) {
    GRPCClient client(config);
    EXPECT_FALSE(client.HealthCheck());
}

TEST_F(GRPCClientTest, ReconnectAttempts) {
    GRPCClient client(config);

    for (int i = 0; i < 3; i++) {
        neuro_pipeline::DetectionResult result;
        result.set_frame_id(i);
        EXPECT_FALSE(client.StreamDetection(result));
    }
}

TEST_F(GRPCClientTest, ConfigValidation) {
    EXPECT_FALSE(config.server_address.empty());
    EXPECT_GT(config.keepalive_interval_ms, 0);
    EXPECT_GT(config.keepalive_timeout_ms, 0);
}
